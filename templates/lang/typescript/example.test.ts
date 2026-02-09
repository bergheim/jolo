import { describe, it, expect } from 'bun:test';

describe('Example tests', () => {
  it('should pass a basic test', () => {
    expect(true).toBe(true);
  });

  it('should perform arithmetic correctly', () => {
    expect(1 + 1).toBe(2);
  });

  it('should handle string operations', () => {
    const result = 'hello'.toUpperCase();
    expect(result).toBe('HELLO');
  });
});
