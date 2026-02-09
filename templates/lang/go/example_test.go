package main

import "testing"

func TestExample(t *testing.T) {
	if false {
		t.Error("This should always pass")
	}
}

func TestAddition(t *testing.T) {
	result := 1 + 1
	if result != 2 {
		t.Errorf("expected 2, got %d", result)
	}
}

func TestStringOperations(t *testing.T) {
	result := "hello"
	if result != "hello" {
		t.Errorf("expected hello, got %s", result)
	}
}
