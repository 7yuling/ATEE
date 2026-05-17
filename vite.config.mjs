import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));

function safeChunkName(value) {
  return value.replace(/^@/, "").replace(/[^A-Za-z0-9_-]+/g, "-");
}

export default defineConfig({
  root: path.join(root, "apps", "admin-console-src"),
  base: "/admin/",
  plugins: [react()],
  build: {
    outDir: path.join(root, "apps", "admin-console"),
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        entryFileNames: "admin.js",
        chunkFileNames: "admin-[name].js",
        manualChunks(id) {
          const normalized = id.split(path.sep).join("/");
          if (!normalized.includes("/node_modules/")) {
            return undefined;
          }
          const antdPath = "/node_modules/antd/";
          if (normalized.includes(antdPath)) {
            const relative = normalized.split(antdPath)[1] || "";
            const parts = relative.split("/");
            if ((parts[0] === "es" || parts[0] === "lib") && parts[1]) {
              return `antd-${safeChunkName(parts[1])}`;
            }
            return "antd-core";
          }
          if (normalized.includes("/node_modules/react/") || normalized.includes("/node_modules/react-dom/")) {
            return "react";
          }
          if (normalized.includes("/node_modules/@ant-design/icons")) {
            return "icons";
          }
          const packagePath = normalized.split("/node_modules/")[1] || "";
          const packageParts = packagePath.split("/");
          if (packageParts[0]?.startsWith("@") && packageParts[1]) {
            return `vendor-${safeChunkName(`${packageParts[0]}-${packageParts[1]}`)}`;
          }
          if (packageParts[0]) {
            return `vendor-${safeChunkName(packageParts[0])}`;
          }
          return "vendor";
        },
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith(".css")) {
            return "styles.css";
          }
          return "admin-[name][extname]";
        },
      },
    },
  },
});
