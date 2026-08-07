/**
 * Build-time image optimizer.
 *
 * Reads source images from src/assets/, resizes them to a sane web width and
 * compresses them, writing the optimized versions to public/ (where Vite
 * serves and bundles them). Non-destructive: the originals in src/assets stay
 * untouched, so re-running is idempotent.
 *
 * Wired as the npm `prebuild` hook, so `npm run build` always ships optimized
 * assets. Run on its own with `npm run optimize:images`.
 */
import { readdir, mkdir, stat } from "node:fs/promises";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC_DIR = join(ROOT, "src", "assets");
const OUT_DIR = join(ROOT, "public");

const MAX_WIDTH = 1600; // banner never needs more than this on screen
const PNG = { quality: 80, compressionLevel: 9, palette: true };
const JPEG = { quality: 80, mozjpeg: true };

const kb = (n) => `${(n / 1024).toFixed(0)} KB`;

async function fileSize(path) {
  try {
    return (await stat(path)).size;
  } catch {
    return 0;
  }
}

async function optimize() {
  let files;
  try {
    files = await readdir(SRC_DIR);
  } catch {
    console.log(`[optimize-images] no ${SRC_DIR} — skipping`);
    return;
  }
  await mkdir(OUT_DIR, { recursive: true });

  const images = files.filter((f) =>
    [".png", ".jpg", ".jpeg", ".webp"].includes(extname(f).toLowerCase()),
  );
  if (images.length === 0) {
    console.log("[optimize-images] no images to optimize");
    return;
  }

  for (const name of images) {
    const inPath = join(SRC_DIR, name);
    const outPath = join(OUT_DIR, name);
    const ext = extname(name).toLowerCase();

    let pipe = sharp(inPath).resize({
      width: MAX_WIDTH,
      withoutEnlargement: true,
    });
    if (ext === ".png") pipe = pipe.png(PNG);
    else if (ext === ".jpg" || ext === ".jpeg") pipe = pipe.jpeg(JPEG);
    else if (ext === ".webp") pipe = pipe.webp({ quality: 80 });

    await pipe.toFile(outPath);
    const before = await fileSize(inPath);
    const after = await fileSize(outPath);
    const pct = before ? Math.round((1 - after / before) * 100) : 0;
    console.log(
      `[optimize-images] ${name}: ${kb(before)} -> ${kb(after)} (-${pct}%)`,
    );
  }
}

optimize().catch((err) => {
  console.error("[optimize-images] failed:", err);
  process.exit(1);
});
