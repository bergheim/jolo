fn main() {
    println!("Hello, world!");
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_example_passes() {
        assert!(true, "This should always pass");
    }

    #[test]
    fn test_addition() {
        let result = 1 + 1;
        assert_eq!(result, 2, "1 + 1 should equal 2");
    }

    #[test]
    fn test_string_operations() {
        let result = "hello".to_uppercase();
        assert_eq!(result, "HELLO");
    }
}
