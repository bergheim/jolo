package main

import (
	"log"
	"net/http"
	"os"

	"{{PROJECT_NAME}}/components"
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "4000"
	}

	mux := http.NewServeMux()
	mux.Handle("GET /static/", http.StripPrefix("/static/", http.FileServer(http.Dir("static"))))
	mux.HandleFunc("GET /", handleHome)
	mux.HandleFunc("GET /api/greet", handleGreet)

	log.Printf("listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}

func handleHome(w http.ResponseWriter, r *http.Request) {
	components.Page("Home", components.Home()).Render(r.Context(), w)
}

func handleGreet(w http.ResponseWriter, r *http.Request) {
	components.Greeting("Hello from the server!").Render(r.Context(), w)
}
