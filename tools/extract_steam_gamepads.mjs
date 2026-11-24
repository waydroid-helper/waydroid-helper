/**
 * Extract the installed Steam client's original SVG controller components.
 * Geometry, stroke widths and glyph colors are kept verbatim. Native input
 * annotations come from comparing the component's own highlight properties;
 * they are not guessed from path order, coordinates, or localized names.
 *
 * Usage: node tools/extract_steam_gamepads.mjs /path/to/steamui/sp.js [output-dir]
 * This is a development tool; neither Node nor Steam is needed at runtime.
 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import crypto from 'node:crypto';

const bundlePath = process.argv[2];
if (!bundlePath) throw new Error('Provide the installed steamui/sp.js path');
const outputDir = process.argv[3] || 'data/gamepads';
const bundle = fs.readFileSync(bundlePath, 'utf8');
const exportStart = bundle.indexOf('GenericGamepadFrontOutline:()=>');
if (exportStart < 0) throw new Error('Steam controller SVG exports were not found');
const source = bundle.slice(bundle.lastIndexOf("t.d(te,{", exportStart));
const components = {
  'generic': 'GenericGamepadFrontOutline',
  'ps3': 'PS3ControllerFrontOutline',
  'ps4': 'PS4ControllerFrontOutline',
  'ps5': 'PS5ControllerFrontOutline',
  'xbox-360': 'Xbox360ControllerFrontOutline',
  'xbox-one': 'XboxOneControllerFrontOutline',
  'switch-pro': 'NintendoSwitchProControllerFrontOutline',
  'joycon-left': 'NintendoJoyConLFrontOutline',
  'joycon-right': 'NintendoJoyConRFrontOutline',
  'joycon-pair': 'NintendoJoyConPairFrontOutline',
  'gamecube': 'GameCubeControllerFrontOutline',
  'steam': 'SteamControllerFrontOutline',
};
const buttonProperties = {
  0: 'highlightSouth', 1: 'highlightEast', 2: 'highlightWest', 3: 'highlightNorth',
  4: 'highlightSelect', 5: 'highlightGuide', 6: 'highlightStart',
  7: 'highlightLeftStick', 8: 'highlightRightStick',
  9: 'highlightLeftBumper', 10: 'highlightRightBumper',
  11: 'highlightDPadUp', 12: 'highlightDPadDown',
  13: 'highlightDPadLeft', 14: 'highlightDPadRight',
  15: 'highlightCapture', 16: 'highlightR4Grip', 17: 'highlightL4Grip',
  18: 'highlightR5Grip', 19: 'highlightL5Grip', 20: 'highlightTouchpad',
};

function functionSource(symbol) {
  const start = source.indexOf(`function ${symbol}(`);
  if (start < 0) throw new Error(`SVG function ${symbol} was not found`);
  let depth = 0, quote = '', escaped = false;
  for (let i = source.indexOf('{', start); i < source.length; i++) {
    const ch = source[i];
    if (quote) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = '';
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth++;
    else if (ch === '}' && --depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`SVG function ${symbol} is incomplete`);
}
function flatten(tree, nodes = []) {
  if (!tree || typeof tree !== 'object') return nodes;
  if (Array.isArray(tree)) { tree.forEach(child => flatten(child, nodes)); return nodes; }
  if (typeof tree.type !== 'string') throw new Error('Unexpected nested SVG component');
  nodes.push(tree);
  flatten(tree.props.children, nodes);
  return nodes;
}
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;');
const preserved = new Set(['viewBox', 'preserveAspectRatio', 'gradientUnits', 'gradientTransform', 'patternUnits', 'clipPathUnits']);
function serialize(node) {
  if (!node || typeof node === 'boolean') return '';
  if (Array.isArray(node)) return node.map(serialize).join('');
  if (typeof node !== 'object') return escape(node);
  const attributes = [];
  for (const [key, value] of Object.entries(node.props)) {
    if (value == null || typeof value === 'function' || typeof value === 'object') continue;
    if (key === 'children' || key === 'ref' || key === 'className' || key.startsWith('on') ||
        key.startsWith('highlight') || key.startsWith('has') || key.startsWith('leftJoystick') ||
        key.startsWith('rightJoystick') || key.startsWith('touchpad') || key.startsWith('bUse')) continue;
    const name = preserved.has(key) || key.startsWith('data-') ? key : key.replace(/[A-Z]/g, ch => '-' + ch.toLowerCase());
    attributes.push(`${name}="${escape(value)}"`);
  }
  // Steam's GenericGamepadEmpty rule sets transparent fill. Its highlighted
  // rule is applied at runtime by the tester to the annotated SVG element.
  if (String(node.props.className).includes('GenericGamepadEmpty') && node.props.fill == null) {
    attributes.push('fill="none"');
  }
  return `<${node.type} ${attributes.join(' ')}>${serialize(node.props.children)}</${node.type}>`;
}
fs.mkdirSync(outputDir, {recursive:true});
const manifest = {};
for (const [file, component] of Object.entries(components)) {
  const alias = source.match(new RegExp(component + ':\\(\\)=>(\\w+)'))?.[1];
  if (!alias) throw new Error(`Steam no longer exports ${component}`);
  const code = functionSource(alias);
  const jsx = (type, props) => ({type, props});
  const context = vm.createContext({
    e: {jsx, jsxs:jsx},
    u: () => new Proxy({}, {get:(_target,key) => String(key)}),
    d: {A:(...args) => args.filter(Boolean).join(' ')},
    // Steam Controller's optional contact geometry hook has no measured DOM
    // rectangle during extraction. Its static SVG remains unchanged.
    l: {l:() => [undefined, () => {}]},
  });
  vm.runInContext(`var component = (${code});`, context, {timeout:1000});
  function render(props = {}) {
    context.input = props;
    return vm.runInContext('component(input)', context, {timeout:1000});
  }
  const tree = render();
  const nodes = flatten(tree);
  let nextId = 0;
  for (const node of nodes) if (!node.props.id) node.props.id = `steam-part-${nextId++}`;
  const original = render();
  const originals = flatten(original);
  const geometryKey = node => JSON.stringify([node.type, ...['d','points','cx','cy','r','x','y','width','height','x1','x2','y1','y2'].map(key=>node.props[key])]);
  const originalIndices = new Map();
  originals.forEach((node,index)=>{
    const key=geometryKey(node);
    if(!originalIndices.has(key)) originalIndices.set(key,[]);
    originalIndices.get(key).push(index);
  });
  function annotate(property, key, value) {
    const changed = flatten(render({[property]:value}));
    const consumed = new Map();
    for (const node of changed) {
      const matchKey=geometryKey(node), occurrence=consumed.get(matchKey)||0;
      consumed.set(matchKey,occurrence+1);
      const index=originalIndices.get(matchKey)?.[occurrence];
      if(index===undefined) {
        // Some native components add an outline only while that input is
        // highlighted. Retain that original path, with conditional visibility.
        if(['path','circle','rect','ellipse','polygon'].includes(node.type)) {
          const added={type:node.type,props:{...node.props,id:`steam-part-${nextId++}`,
            [key]:property,'data-conditional':key,display:'none'}};
          tree.props.children=[...tree.props.children,added];
          nodes.push(added);
        }
        continue;
      }
      const before=originals[index].props;
      if (node.props.className !== before.className || node.props.stroke !== before.stroke ||
          node.props.fill !== before.fill || JSON.stringify(node.props.style) !== JSON.stringify(before.style)) {
        nodes[index].props[key] = property;
        if (key.startsWith('data-stick-')) {
          const transform = node.props.style?.transform || '';
          const axis = property.endsWith('X') ? 'x' : 'y';
          const match = transform.match(new RegExp('translate' + axis.toUpperCase() + '\\(([-0-9.]+)%\\)'));
          if (!match) throw new Error(`${component}: unrecognized native stick transform ${transform}`);
          const viewBox = tree.props.viewBox.split(/\s+/).map(Number);
          nodes[index].props['data-stick-' + axis + '-travel'] = Number(match[1]) * viewBox[axis==='x' ? 2 : 3] / 100;
        }
      }
    }
  }
  for (const [button, property] of Object.entries(buttonProperties)) {
    annotate(property, 'data-button-' + button, true);
  }
  annotate('highlightLeftTrigger', 'data-axis-4', true);
  annotate('highlightRightTrigger', 'data-axis-5', true);
  annotate('leftJoystickX', 'data-stick-0', 1);
  annotate('rightJoystickX', 'data-stick-1', 1);
  annotate('leftJoystickY', 'data-stick-0', 1);
  annotate('rightJoystickY', 'data-stick-1', 1);
  nodes.forEach(node=>{
    if(node.props['data-button-20']) node.props['data-touchpad']='center';
  });
  tree.props.color = '#d7dadc';
  tree.props.xmlns = 'http://www.w3.org/2000/svg';
  const svg = '<?xml version="1.0" encoding="UTF-8"?>\n' + serialize(tree) + '\n';
  fs.writeFileSync(path.join(outputDir,file+'.svg'),svg);
  manifest[file] = {component, paths:nodes.filter(node=>node.type==='path').length,
    buttons:Object.keys(buttonProperties).filter(button=>nodes.some(node=>node.props['data-button-'+button])),
    sticks:[0,1].filter(stick=>nodes.some(node=>node.props['data-stick-'+stick]))};
  console.log(file, JSON.stringify(manifest[file]));
}
const hash = crypto.createHash('sha256').update(bundle).digest('hex');
fs.writeFileSync(path.join(outputDir,'steam-manifest.json'),JSON.stringify({bundle_sha256:hash, components:manifest},null,2)+'\n');
fs.writeFileSync(path.join(outputDir,'NOTICE.txt'),
  'Original controller SVG geometry extracted from the installed Valve Steam client.\n'+
  'Source: steamui/sp.js, controller outline components listed in steam-manifest.json.\n'+
  'SVG paths, original strokes, proportions and glyph colors are preserved.\n'+
  'Runtime input annotations and stable element IDs were added by Waydroid Helper.\n'+
  'These Valve assets are not relicensed under Waydroid Helper\'s GPL license.\n'+
  'Extraction tool: tools/extract_steam_gamepads.mjs\n'+
  'Source bundle SHA-256: '+hash+'\n');
