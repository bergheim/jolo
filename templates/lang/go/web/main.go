package main

import (
	"log"
	"net/http"
	"net/http/pprof"
	"os"

	"{{PROJECT_NAME}}/components"
)

func main() {
	port := os.Getenv("APP_PORT")
	if port == "" {
		port = os.Getenv("PORT")
	}
	if port == "" {
		port = "4000"
	}

	mux := http.NewServeMux()
	mux.Handle("GET /static/", http.StripPrefix("/static/", http.FileServer(http.Dir("static"))))
	mux.HandleFunc("GET /", handleHome)
	mux.HandleFunc("GET /api/greet", handleGreet)
	if os.Getenv("APP_PROFILE") != "0" {
		mux.HandleFunc("GET /debug/pprof/", pprof.Index)
		mux.HandleFunc("GET /debug/pprof/cmdline", pprof.Cmdline)
		mux.HandleFunc("GET /debug/pprof/profile", pprof.Profile)
		mux.HandleFunc("GET /debug/pprof/symbol", pprof.Symbol)
		mux.HandleFunc("GET /debug/pprof/trace", pprof.Trace)
	}

	log.Printf("listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}

func handleHome(w http.ResponseWriter, r *http.Request) {
	components.Page("Home", components.Home()).Render(r.Context(), w)
}

func handleGreet(w http.ResponseWriter, r *http.Request) {
	components.Greeting("Hello from the server!").Render(r.Context(), w)
}
