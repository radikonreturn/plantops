import { existsSync, readFileSync, statSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import ts from 'typescript';
import { fileURLToPath } from 'node:url';

const nativeRequire = createRequire(import.meta.url);
export function typescriptLoader(overrides = {}) {
  const cache = new Map();
  function load(path) {
    const file = ['', '.ts', '.tsx', '/index.tsx'].map(ext => path + ext).find(file => existsSync(file) && statSync(file).isFile());
    if (!file) throw Error(`Missing test module: ${path}`);
    if (cache.has(file)) return cache.get(file).exports;
    const module = { exports: {} };
    cache.set(file, module);
    const source = readFileSync(file, 'utf8').replace('import.meta.env', '({})');
    const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
    const require = id => {
      if (id in overrides) return overrides[id];
      if (id.endsWith('.css')) return {};
      return id.startsWith('.') ? load(resolve(dirname(file), id)) : nativeRequire(id);
    };
    new Function('require', 'module', 'exports', code)(require, module, module.exports);
    return module.exports;
  }
  return path => load(resolve(fileURLToPath(new URL('../src/', import.meta.url)), path));
}
