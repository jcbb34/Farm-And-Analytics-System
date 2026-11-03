import { createRequire } from "node:module";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const require = createRequire(import.meta.url);
const { loadBindings, parse } = require("next/dist/build/swc");
const root = path.resolve(import.meta.dirname, "..");
const directories = ["src", "tests", "browser-tests", "scripts"];
const extensions = new Set([".js", ".jsx", ".mjs"]);

async function* sources(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
        const fullPath = path.join(directory, entry.name);
        if (entry.isDirectory()) {
            yield* sources(fullPath);
        } else if (entry.isFile() && extensions.has(path.extname(entry.name))) {
            yield fullPath;
        }
    }
}

await loadBindings();
const failures = [];
let checked = 0;

for (const directory of directories) {
    for await (const filename of sources(path.join(root, directory))) {
        try {
            await parse(await readFile(filename, "utf8"), { filename });
            checked += 1;
        } catch (error) {
            failures.push(`${path.relative(root, filename)}: ${error.message}`);
        }
    }
}

for (const failure of failures) console.error(failure);
console.log(`Parsed ${checked} JavaScript/JSX files; ${failures.length} failed.`);
if (failures.length) process.exitCode = 1;
