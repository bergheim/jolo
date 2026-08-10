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
 *   --screenshot      Take screenshot (saves to scratch/screenshot.png or --output)
 *   --pdf             Generate PDF (saves to scratch/page.pdf or --output)
 *   --output <path>   Output path for screenshot/pdf
 *   --width <list>    Viewport width(s), e.g. 320,390,430 (repeatable)
 *   --height <px>     Viewport height with --width (default: 844)
 *   --overflow        Report horizontal overflow; exits 1 if anything overflows
 *   --wait <ms>       Wait time after load (default: 1000)
 *   --timeout <ms>    Navigation timeout (default: 30000)
 *   --full-page       Full page screenshot
 *   --describe        Output page title and basic info
 *   --snapshot        Output text content preview
 *   --aria            Output ARIA accessibility tree (like agent-browser)
 *   --interactive     With --aria, only show interactive elements
 *   --json            Output results as JSON
 *
 * Exit codes: 0 ok, 1 overflow detected (or no url), 2 usage/fatal error.
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);

// Flags that consume the following token. The url scan needs this so that
// `--width 320 http://x` doesn't treat the operand `320` as the target.
const VALUED_FLAGS = new Set(['output', 'wait', 'timeout', 'width', 'height']);

const DEFAULT_HEIGHT = 844;

function getArg(name, defaultValue = null) {
  const idx = args.indexOf(`--${name}`);
  if (idx === -1) return defaultValue;
  if (idx + 1 < args.length && !args[idx + 1].startsWith('--')) {
    return args[idx + 1];
  }
  return true;
}

// Every operand of a repeated flag, in order. getArg only sees the first.
function getArgAll(name) {
  const found = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] !== `--${name}`) continue;
    const value = args[i + 1];
    if (value !== undefined && !value.startsWith('--')) found.push(value);
  }
  return found;
}

function hasFlag(name) {
  return args.includes(`--${name}`);
}

function findUrl() {
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (!arg.startsWith('--')) return arg;
    if (VALUED_FLAGS.has(arg.slice(2)) && args[i + 1] && !args[i + 1].startsWith('--')) {
      i++;
    }
  }
  return undefined;
}

function usageError(message) {
  console.error(`error: ${message}`);
  process.exit(2);
}

// null means "no --width given": one viewport at Playwright's default, and
// every output path is written verbatim.
function parseWidths() {
  if (!hasFlag('width')) return null;
  const raw = getArgAll('width');
  if (raw.length === 0) usageError('--width requires a value, e.g. --width 320,390,430');

  const widths = [];
  for (const chunk of raw) {
    for (const piece of chunk.split(',')) {
      const token = piece.trim();
      if (!token) continue;
      if (!/^\d+$/.test(token)) usageError(`invalid --width value: ${token}`);
      const value = parseInt(token, 10);
      if (value < 1 || value > 10000) usageError(`--width out of range (1-10000): ${token}`);
      if (!widths.includes(value)) widths.push(value);
    }
  }
  if (widths.length === 0) usageError('--width requires a value, e.g. --width 320,390,430');
  return widths;
}

function parseHeight() {
  if (!hasFlag('height')) return DEFAULT_HEIGHT;
  const raw = getArg('height');
  if (raw === true) usageError('--height requires a value, e.g. --height 844');
  if (!/^\d+$/.test(raw)) usageError(`invalid --height value: ${raw}`);
  const value = parseInt(raw, 10);
  if (value < 1 || value > 10000) usageError(`--height out of range (1-10000): ${raw}`);
  return value;
}

// shots/page.png + 320 -> shots/page-320.png. Note the slice must be computed
// from the length: with no extension, -ext.length is -0, which slices to "".
function withWidthSuffix(target, width) {
  const ext = path.extname(target);
  const base = target.slice(0, target.length - ext.length);
  return `${base}-${width}${ext}`;
}

function writeTo(target, width, multi) {
  const resolved = multi ? withWidthSuffix(target, width) : target;
  fs.mkdirSync(path.dirname(resolved), { recursive: true });
  return resolved;
}

/**
 * Runs in the page. Reports elements that make the page scroll sideways.
 *
 * Deliberately narrow, because a noisy overflow report is a useless one:
 * anything inside a scroll or clip container is that container's business, a
 * flagged ancestor suppresses its descendants so the outermost culprit is
 * named once, and html/body are covered by the document-level check rather
 * than reported as two more offenders.
 */
function collectOverflow() {
  const TOLERANCE = 1;
  const CLIPPING = /^(auto|scroll|hidden|clip)$/;
  const viewportWidth = window.innerWidth;

  const selectorFor = (el) => {
    const tag = el.tagName.toLowerCase();
    if (el.id) return `${tag}#${el.id}`;
    const classes = typeof el.className === 'string'
      ? el.className.trim().split(/\s+/).filter(Boolean).slice(0, 2)
      : [];
    if (classes.length) return `${tag}.${classes.join('.')}`;
    const parent = el.parentElement;
    if (!parent) return tag;
    const index = Array.prototype.indexOf.call(parent.children, el) + 1;
    return `${parent.tagName.toLowerCase()} > ${tag}:nth-child(${index})`;
  };

  const offenders = [];
  const flagged = new Set();

  for (const el of document.body ? document.body.querySelectorAll('*') : []) {
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
    // Fixed elements are out of flow: they never contribute document scroll.
    if (style.position === 'fixed') continue;

    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) continue;
    // Entirely off to the left is the sr-only / off-canvas pattern, not
    // sideways page scroll.
    if (rect.right <= 0) continue;

    let suppressed = false;
    for (let parent = el.parentElement; parent; parent = parent.parentElement) {
      if (flagged.has(parent)) { suppressed = true; break; }
      const parentStyle = getComputedStyle(parent);
      if (CLIPPING.test(parentStyle.overflowX) || parentStyle.position === 'fixed') {
        suppressed = true;
        break;
      }
    }
    if (suppressed) continue;

    const tag = el.tagName.toLowerCase();
    const extendsPast = rect.right > viewportWidth + TOLERANCE;
    // clientWidth is 0 on inline elements, and a form control with a long
    // value always out-scrolls its box without affecting the page.
    const scrollsSelf = !CLIPPING.test(style.overflowX)
      && !['input', 'textarea', 'select'].includes(tag)
      && el.clientWidth > 0
      && el.scrollWidth > el.clientWidth + TOLERANCE;

    if (!extendsPast && !scrollsSelf) continue;

    flagged.add(el);
    offenders.push({
      selector: selectorFor(el),
      tag,
      width: Math.round(Math.max(rect.width, el.scrollWidth)),
      right: Math.round(rect.right),
      reason: extendsPast ? 'extends past viewport' : 'scrolls horizontally',
    });
  }

  const documentScrollWidth = document.documentElement.scrollWidth;
  return {
    viewportWidth,
    documentScrollWidth,
    documentOverflows: documentScrollWidth > viewportWidth + TOLERANCE,
    offenders,
  };
}

async function checkViewport(browser, viewport, options) {
  const { url, multi, wantJson } = options;
  const result = {
    width: viewport ? viewport.width : null,
    height: viewport ? viewport.height : null,
    success: false,
    console: [],
    errors: [],
    title: null,
    snapshot: null,
    aria: null,
    refs: {},
    screenshot: null,
    pdf: null,
    overflow: null,
  };

  // Omit the key entirely when there's no --width so Playwright keeps its own
  // default; `viewport: null` would mean something else (match the window).
  const context = await browser.newContext(viewport ? { viewport } : {});

  try {
    const page = await context.newPage();

    if (options.wantConsole) {
      page.on('console', msg => {
        const entry = { type: msg.type(), text: msg.text() };
        result.console.push(entry);
        if (!wantJson) {
          const prefix = msg.type() === 'error' ? '[ERR]' :
                        msg.type() === 'warning' ? '[WARN]' : '[LOG]';
          console.log(`${prefix} [console.${msg.type()}] ${msg.text()}`);
        }
      });
    }

    if (options.wantErrors) {
      page.on('pageerror', err => {
        const entry = { message: err.message, stack: err.stack };
        result.errors.push(entry);
        if (!wantJson) {
          console.log(`[PAGE ERROR] ${err.message}`);
        }
      });
    }

    if (!wantJson) console.log(`Navigating to ${url}...`);

    try {
      await page.goto(url, { timeout: options.timeout, waitUntil: 'load' });
      result.success = true;
    } catch (navError) {
      result.navigationError = navError.message;
      if (!wantJson) console.log(`Navigation failed: ${navError.message}`);
    }

    if (options.waitTime > 0) {
      await page.waitForTimeout(options.waitTime);
    }

    result.title = await page.title();

    if (options.wantDescribe && !wantJson) {
      console.log(`\nPage: ${result.title}`);
      console.log(`URL: ${page.url()}`);
    }

    if (options.wantSnapshot) {
      result.snapshot = await page.evaluate(() => {
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
        console.log(`\nContent preview:\n${(result.snapshot || '').substring(0, 500)}...`);
      }
    }

    if (options.wantAria) {
      // Use Playwright's ariaSnapshot API
      let ariaSnapshot = await page.locator('body').ariaSnapshot();

      // If interactive only, filter to just interactive elements
      if (options.wantInteractive) {
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

      result.aria = ariaSnapshot;
      result.refs = refs;

      if (!wantJson) {
        console.log(`\nARIA tree${options.wantInteractive ? ' (interactive only)' : ''}:`);
        console.log(result.aria);
        console.log(`\nRefs: ${Object.keys(refs).length} interactive elements`);
      }
    }

    if (options.wantScreenshot) {
      const screenshotPath = writeTo(options.output || 'scratch/screenshot.png', result.width, multi);
      await page.screenshot({ path: screenshotPath, fullPage: options.fullPage });
      result.screenshot = screenshotPath;
      if (!wantJson) console.log(`Screenshot saved: ${screenshotPath}`);
    }

    if (options.wantPdf) {
      const pdfPath = writeTo(options.output || 'scratch/page.pdf', result.width, multi);
      await page.pdf({ path: pdfPath });
      result.pdf = pdfPath;
      if (!wantJson) console.log(`PDF saved: ${pdfPath}`);
    }

    if (options.wantOverflow) {
      result.overflow = await page.evaluate(collectOverflow);
      if (!wantJson) {
        const { offenders, documentOverflows, documentScrollWidth, viewportWidth } = result.overflow;
        if (documentOverflows || offenders.length > 0) {
          console.log(`\nOVERFLOW at ${viewportWidth}px (document scrollWidth ${documentScrollWidth}):`);
          for (const item of offenders) {
            console.log(`  ${item.selector}  <${item.tag}>  ${item.width}px (right edge ${item.right}px) > viewport ${viewportWidth}px  [${item.reason}]`);
          }
          if (offenders.length === 0) {
            console.log('  no single element identified - check margins/padding on html or body');
          }
        } else {
          console.log(`\nNo horizontal overflow at ${viewportWidth}px.`);
        }
      }
    }

    if (!wantJson) {
      if (result.console.length > 0 || result.errors.length > 0) {
        console.log(`\nSummary:`);
        console.log(`  Console messages: ${result.console.length}`);
        console.log(`  Page errors: ${result.errors.length}`);
      }
    }
  } finally {
    await context.close().catch(() => {});
  }

  return result;
}

async function main() {
  const url = findUrl();

  if (!url || hasFlag('help')) {
    console.log(`Usage: browser-check <url> [options]

<url> may be http(s):// or file:// - a file:// path is the normal way to check
a static prototype before it becomes a page.

Options:
  --console       Capture console logs
  --errors        Capture page errors (JS exceptions)
  --screenshot    Take screenshot
  --pdf           Generate PDF
  --output <path> Output path for screenshot/pdf
  --width <list>  Viewport width(s): 320,390,430 or a repeated --width.
                  Each width is checked in its own context, one browser launch.
                  With more than one, outputs are suffixed: shot-320.png
  --height <px>   Viewport height, used with --width (default: 844)
  --overflow      Report horizontal overflow at each width. Exits 1 if the page
                  scrolls sideways or an element extends past the viewport
  --wait <ms>     Wait time after load (default: 1000)
  --timeout <ms>  Navigation timeout (default: 30000)
  --full-page     Full page screenshot
  --describe      Output page title and basic info
  --snapshot      Output simplified page content
  --aria          Output ARIA accessibility tree
  --interactive   With --aria, only show interactive elements
  --json          Output results as JSON

Examples:
  browser-check https://localhost:4000 --console --errors
  browser-check https://example.com --screenshot --output shot.png
  browser-check file:///tmp/prototype.html --screenshot --width 320,390,430 --output scratch/proto.png
  browser-check http://localhost:$PORT --overflow --width 320,390,430
  browser-check https://myapp.com --console --errors --screenshot --json`);
    process.exit(url ? 0 : 1);
  }

  const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ||
                         process.env.CHROME_PATH ||
                         '/usr/bin/chromium-browser';

  const widths = parseWidths();
  const height = parseHeight();
  const wantPdf = hasFlag('pdf');
  const wantJson = hasFlag('json');

  if (!widths && hasFlag('height')) {
    usageError('--height only applies with --width');
  }
  // page.pdf() renders print media at paper size and ignores the viewport, so
  // N widths would write N byte-identical files under N different names.
  if (wantPdf && widths && widths.length > 1) {
    usageError('--pdf takes a single --width: PDF output ignores the viewport');
  }

  const options = {
    url,
    multi: Boolean(widths && widths.length > 1),
    wantConsole: hasFlag('console'),
    wantErrors: hasFlag('errors'),
    wantScreenshot: hasFlag('screenshot'),
    wantPdf,
    wantDescribe: hasFlag('describe'),
    wantSnapshot: hasFlag('snapshot'),
    wantAria: hasFlag('aria'),
    wantInteractive: hasFlag('interactive'),
    wantOverflow: hasFlag('overflow'),
    wantJson,
    fullPage: hasFlag('full-page'),
    output: getArg('output'),
    waitTime: parseInt(getArg('wait', '1000')),
    timeout: parseInt(getArg('timeout', '30000')),
  };

  const viewports = widths
    ? widths.map(width => ({ width, height }))
    : [null];

  const results = { url, success: false, title: null, viewports: [] };

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

    for (const viewport of viewports) {
      if (viewport && !wantJson) {
        console.log(`\n=== viewport ${viewport.width}x${viewport.height} ===`);
      }
      results.viewports.push(await checkViewport(browser, viewport, options));
    }

    results.success = results.viewports.every(v => v.success);
    results.title = results.viewports.length ? results.viewports[0].title : null;

    if (wantJson) {
      console.log(JSON.stringify(results, null, 2));
    }

    if (options.wantOverflow) {
      // A page that never loaded has nothing to overflow. Reporting 0 would be
      // a green light for a dead server.
      if (!results.success) process.exit(1);
      const overflowed = results.viewports.some(v =>
        v.overflow && (v.overflow.documentOverflows || v.overflow.offenders.length > 0));
      if (overflowed) process.exit(1);
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
