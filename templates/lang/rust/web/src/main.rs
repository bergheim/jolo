use std::{env, sync::Arc, time::Duration};

use axum::{
    extract::{Query, State},
    http::{header, StatusCode},
    response::{Html, IntoResponse, Response},
    routing::get,
    Router,
};
use axum_htmx::HxRequest;
use minijinja::{context, Environment};
use pprof::ProfilerGuard;
use serde::Deserialize;
use tower_http::services::ServeDir;
use tower_livereload::LiveReloadLayer;

struct AppState {
    env: Environment<'static>,
}

#[derive(Deserialize)]
struct ProfileQuery {
    seconds: Option<u64>,
}

#[tokio::main]
async fn main() {
    let port = env::var("PORT").unwrap_or_else(|_| "4000".into());

    let mut env = Environment::new();
    env.set_loader(minijinja::path_loader("templates"));

    let state = Arc::new(AppState { env });

    let mut app = Router::new()
        .route("/", get(handle_home))
        .route("/api/greet", get(handle_greet))
        .nest_service("/static", ServeDir::new("static"));

    if env::var("APP_PROFILE")
        .map(|value| value != "0")
        .unwrap_or(true)
    {
        app = app.route("/debug/pprof/profile", get(handle_profile));
    }

    let app = app.layer(LiveReloadLayer::new()).with_state(state);

    let addr = format!("0.0.0.0:{port}");
    println!("listening on {addr}");
    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

async fn handle_home(State(state): State<Arc<AppState>>) -> Html<String> {
    let tmpl = state.env.get_template("index.html").unwrap();
    Html(tmpl.render(context! { title => "Home" }).unwrap())
}

async fn handle_greet(
    HxRequest(is_htmx): HxRequest,
    State(state): State<Arc<AppState>>,
) -> Html<String> {
    if is_htmx {
        Html("<p>Hello from the server!</p>".into())
    } else {
        let tmpl = state.env.get_template("index.html").unwrap();
        Html(tmpl.render(context! { title => "Greeting" }).unwrap())
    }
}

async fn handle_profile(
    Query(query): Query<ProfileQuery>,
) -> Result<Response, (StatusCode, String)> {
    let seconds = query.seconds.unwrap_or(5).clamp(1, 30);
    let svg = tokio::task::spawn_blocking(move || -> Result<Vec<u8>, String> {
        let guard = ProfilerGuard::new(100).map_err(|err| err.to_string())?;
        std::thread::sleep(Duration::from_secs(seconds));
        let report = guard.report().build().map_err(|err| err.to_string())?;
        let mut svg = Vec::new();
        report
            .flamegraph(&mut svg)
            .map_err(|err| err.to_string())?;
        Ok(svg)
    })
    .await
    .map_err(|err| (StatusCode::INTERNAL_SERVER_ERROR, err.to_string()))?
    .map_err(|err| (StatusCode::INTERNAL_SERVER_ERROR, err))?;

    Ok(([(header::CONTENT_TYPE, "image/svg+xml")], svg).into_response())
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::Request;
    use tower::ServiceExt;

    fn app() -> Router {
        let mut env = Environment::new();
        env.set_loader(minijinja::path_loader("templates"));
        let state = Arc::new(AppState { env });

        Router::new()
            .route("/", get(handle_home))
            .route("/api/greet", get(handle_greet))
            .with_state(state)
    }

    #[tokio::test]
    async fn home_returns_html() {
        let resp = app()
            .oneshot(Request::get("/").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(resp.status(), 200);
    }

    #[tokio::test]
    async fn greet_htmx_returns_fragment() {
        let resp = app()
            .oneshot(
                Request::get("/api/greet")
                    .header("HX-Request", "true")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), 200);
    }
}
