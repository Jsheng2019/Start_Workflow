// Simple module used to verify the build step in CI workflows
// Used by: ci.yml, deploy.yml, release.yml

/**
 * Adds two numbers together
 */
function add(a, b) {
  return a + b;
}

/**
 * Returns a greeting message
 */
function greet(name) {
  return `Hello, ${name}! Welcome to GitHub Actions.`;
}

module.exports = { add, greet };

// When run directly via "node src/index.js" (build script), prints confirmation
if (require.main === module) {
  console.log(greet('Developer'));
  console.log(`add(2, 3) = ${add(2, 3)}`);
  console.log('Build completed successfully.');
}
