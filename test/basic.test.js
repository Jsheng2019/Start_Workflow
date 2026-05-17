// Tests using Node.js built-in test runner (available in Node 18+)
// Used by: ci.yml, release.yml

const { describe, it } = require('node:test');
const assert = require('node:assert');
const { add, greet } = require('../src/index');

describe('add()', () => {
  it('should add two positive numbers', () => {
    assert.strictEqual(add(2, 3), 5);
  });

  it('should handle negative numbers', () => {
    assert.strictEqual(add(-1, -2), -3);
  });

  it('should handle zero', () => {
    assert.strictEqual(add(5, 0), 5);
  });
});

describe('greet()', () => {
  it('should return a greeting with the given name', () => {
    const result = greet('World');
    assert.ok(result.includes('Hello'));
    assert.ok(result.includes('World'));
  });
});
