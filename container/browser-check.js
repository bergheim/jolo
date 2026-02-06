#!/usr/bin/env node
/**
 * browser-check - Browser automation CLI for Alpine/musl
 * Uses Playwright API with system Chromium
 * Alternative to agent-browser that works on musl systems
 *
 * Usage:
 *   browser-check <url> [options]
 *
 * Options:
 *   --console         Capture console logs
 *   --errors          Capture page errors (JS exceptions)
 *   --screenshot      Take screenshot (saves to ./screenshot.png or --output)
 *   --pdf             Generate PDF (saves to ./page.pdf or --output)
 *   --output <path>   Output path for screenshot/pdf
 *   --wait <ms>       Wait time after load (default: 1000)
 *   --timeout <ms>    Navigation timeout (default: 30000)
 *   --full-page       Full page screenshot
 *   --describe        Output page title and basic info
 *   --snapshot        Output text content preview
 *   --aria            Output ARIA accessibility tree (like agent-browser)
 *   --interactive     With --aria, only show interactive elements
 *   --json            Output results as JSON
 */

const { chromium } = require('playwright');

const args = process.argv.slice(2);

function getArg(name, defaultValue = null) {
  const idx = args.indexOf(`--${name}`);
  if (idx === -1) return defaultValue;
  if (idx + 1 < args.length && !args[idx + 1].startsWith('--')) {
    return args[idx + 1];
  }
  return true;
}

function hasFlag(name) {
  return args.includes(`--${name}`);
}

async function main() {
  const url = args.find(a => !a.startsWith('--'));

  if (!url || hasFlag('help')) {
    console.log(`Usage: browser-check <url> [options]

Options:
  --console       Capture console logs
  --errors        Capture page errors (JS exceptions)
  --screenshot    Take screenshot
  --pdf           Generate PDF
  --output <path> Output path for screenshot/pdf
  --wait <ms>     Wait time after load (default: 1000)
  --timeout <ms>  Navigation timeout (default: 30000)
  --full-page     Full page screenshot
  --describe      Output page title and basic info
  --snapshot      Output simplified page content
  --json          Output results as JSON

Examples:
  browser-check https://localhost:4000 --console --errors
  browser-check https://example.com --screenshot --output shot.png
  browser-check https://myapp.com --console --errors --screenshot --json`);
    process.exit(url ? 0 : 1);
  }

  const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ||
                         process.env.CHROME_PATH ||
                         '/usr/bin/chromium-browser';

  const wantConsole = hasFlag('console');
  const wantErrors = hasFlag('errors');
  const wantScreenshot = hasFlag('screenshot');
  const wantPdf = hasFlag('pdf');
  const wantDescribe = hasFlag('describe');
  const wantSnapshot = hasFlag('snapshot');
  const wantAria = hasFlag('aria');
  const wantInteractive = hasFlag('interactive');
  const wantJson = hasFlag('json');
  const fullPage = hasFlag('full-page');
  const output = getArg('output');
  const waitTime = parseInt(getArg('wait', '1000'));
  const timeout = parseInt(getArg('timeout', '30000'));

  const results = {
    url,
    success: false,
    console: [],
    errors: [],
    title: null,
    snapshot: null,
    aria: null,
    refs: {},
    screenshot: null,
    pdf: null
  };

  let browser;
  try {
    browser = await chromium.launch({
      executablePath,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu'
      ]
    });

    const page = await browser.newPage();

    // Set up console capture
    if (wantConsole) {
      page.on('console', msg => {
        const entry = { type: msg.type(), text: msg.text() };
        results.console.push(entry);
        if (!wantJson) {
          const prefix = msg.type() === 'error' ? '[ERR]' :
                        msg.type() === 'warning' ? '[WARN]' : '[LOG]';
          console.log(`${prefix} [console.${msg.type()}] ${msg.text()}`);
        }
      });
    }

    // Set up error capture
    if (wantErrors) {
      page.on('pageerror', err => {
        const entry = { message: err.message, stack: err.stack };
        results.errors.push(entry);
        if (!wantJson) {
          console.log(`[PAGE ERROR] ${err.message}`);
        }
      });
    }

    // Navigate
    if (!wantJson) console.log(`Navigating to ${url}...`);

    try {
      await page.goto(url, { timeout, waitUntil: 'load' });
      results.success = true;
    } catch (navError) {
      results.navigationError = navError.message;
      if (!wantJson) console.log(`Navigation failed: ${navError.message}`);
    }

    // Wait for additional content
    if (waitTime > 0) {
      await page.waitForTimeout(waitTime);
    }

    // Get title
    results.title = await page.title();

    if (wantDescribe && !wantJson) {
      console.log(`\nPage: ${results.title}`);
      console.log(`URL: ${page.url()}`);
    }

    // Get snapshot (text content)
    if (wantSnapshot) {
      results.snapshot = await page.evaluate(() => {
        // Get text content, simplified
        const getText = (el) => {
          if (el.nodeType === Node.TEXT_NODE) {
            return el.textContent.trim();
          }
          if (el.nodeType !== Node.ELEMENT_NODE) return '';

          const tag = el.tagName.toLowerCase();
          if (['script', 'style', 'noscript'].includes(tag)) return '';

          const children = Array.from(el.childNodes).map(getText).filter(Boolean);
          return children.join(' ');
        };
        return getText(document.body).replace(/\s+/g, ' ').trim().substring(0, 2000);
      });

      if (!wantJson) {
        console.log(`\nContent preview:\n${results.snapshot.substring(0, 500)}...`);
      }
    }

    // Get ARIA accessibility tree (like agent-browser)
    if (wantAria) {
      // Use Playwright's ariaSnapshot API
      let ariaSnapshot = await page.locator('body').ariaSnapshot();

      // If interactive only, filter to just interactive elements
      if (wantInteractive) {
        const lines = ariaSnapshot.split('\n');
        const interactiveRoles = ['link', 'button', 'textbox', 'checkbox', 'radio',
          'combobox', 'menuitem', 'tab', 'switch', 'slider', 'spinbutton', 'searchbox'];
        const filtered = lines.filter(line => {
          const trimmed = line.trim();
          return interactiveRoles.some(role => trimmed.startsWith(`- ${role} `) || trimmed.startsWith(`- ${role}:`));
        });
        ariaSnapshot = filtered.join('\n');
      }

      // Add refs to interactive elements
      let refCounter = 1;
      const refs = {};
      const interactiveRoles = ['link', 'button', 'textbox', 'checkbox', 'radio',
        'combobox', 'menuitem', 'tab', 'switch', 'slider', 'spinbutton', 'searchbox'];

      ariaSnapshot = ariaSnapshot.split('\n').map(line => {
        for (const role of interactiveRoles) {
          // Match patterns like "- link "text"" or "- button "text":"
          const pattern = new RegExp(`^(\\s*- ${role} ".*?")(.*)$`);
          const match = line.match(pattern);
          if (match) {
            const ref = `e${refCounter++}`;
            // Extract name from the line
            const nameMatch = line.match(/"([^"]+)"/);
            const name = nameMatch ? nameMatch[1] : '';
            refs[ref] = { name, role };
            return `${match[1]} [ref=${ref}]${match[2]}`;
          }
        }
        return line;
      }).join('\n');

      results.aria = ariaSnapshot;
      results.refs = refs;

      if (!wantJson) {
        console.log(`\nARIA tree${wantInteractive ? ' (interactive only)' : ''}:`);
        console.log(results.aria);
        console.log(`\nRefs: ${Object.keys(refs).length} interactive elements`);
      }
    }

    // Screenshot
    if (wantScreenshot) {
      const screenshotPath = output || 'screenshot.png';
      await page.screenshot({ path: screenshotPath, fullPage });
      results.screenshot = screenshotPath;
      if (!wantJson) console.log(`Screenshot saved: ${screenshotPath}`);
    }

    // PDF
    if (wantPdf) {
      const pdfPath = output || 'page.pdf';
      await page.pdf({ path: pdfPath });
      results.pdf = pdfPath;
      if (!wantJson) console.log(`PDF saved: ${pdfPath}`);
    }

    await browser.close();

    // Summary
    if (!wantJson) {
      if (results.console.length > 0 || results.errors.length > 0) {
        console.log(`\nSummary:`);
        console.log(`  Console messages: ${results.console.length}`);
        console.log(`  Page errors: ${results.errors.length}`);
      }
    }

    if (wantJson) {
      console.log(JSON.stringify(results, null, 2));
    }

    // Exit with error if there were page errors
    if (results.errors.length > 0) {
      process.exit(1);
    }

  } catch (err) {
    results.fatalError = err.message;
    if (wantJson) {
      console.log(JSON.stringify(results, null, 2));
    } else {
      console.error(`Fatal error: ${err.message}`);
    }
    process.exit(2);
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}

main();
