use std::{env, sync::Arc};

use axum::{
    extract::State,
    response::Html,
    routing::get,
    Router,
};
use axum_htmx::HxRequest;
use minijinja::{context, Environment};
use tower_http::services::ServeDir;
use tower_livereload::LiveReloadLayer;

struct AppState {
    env: Environment<'static>,
}

#[tokio::main]
async fn main() {
    let port = env::var("PORT").unwrap_or_else(|_| "4000".into());

    let mut env = Environment::new();
    env.set_loader(minijinja::path_loader("templates"));

    let state = Arc::new(AppState { env });

    let app = Router::new()
        .route("/", get(handle_home))
        .route("/api/greet", get(handle_greet))
        .nest_service("/static", ServeDir::new("static"))
        .layer(LiveReloadLayer::new())
        .with_state(state);

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
