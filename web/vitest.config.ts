import path from "node:path";

import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      {
        find: "@aegroup/agent-core-web-shell/styles.css",
        replacement: path.resolve(__dirname, "../packages/web-shell/src/styles.css"),
      },
      {
        find: /^@aegroup\/agent-core-web-shell$/,
        replacement: path.resolve(__dirname, "../packages/web-shell/src/index.ts"),
      },
      {
        find: /^tailwindcss$/,
        replacement: path.resolve(__dirname, "./node_modules/tailwindcss/index.css"),
      },
      {
        find: /^tw-animate-css$/,
        replacement: path.resolve(__dirname, "./node_modules/tw-animate-css/dist/tw-animate.css"),
      },
      { find: "react", replacement: path.resolve(__dirname, "./node_modules/react") },
      { find: "react/jsx-runtime", replacement: path.resolve(__dirname, "./node_modules/react/jsx-runtime.js") },
      { find: "react/jsx-dev-runtime", replacement: path.resolve(__dirname, "./node_modules/react/jsx-dev-runtime.js") },
      { find: "react-dom", replacement: path.resolve(__dirname, "./node_modules/react-dom") },
      { find: "react-router-dom", replacement: path.resolve(__dirname, "./node_modules/react-router-dom") },
      { find: "lucide-react", replacement: path.resolve(__dirname, "./node_modules/lucide-react") },
      { find: "@azure/msal-browser", replacement: path.resolve(__dirname, "./node_modules/@azure/msal-browser") },
      { find: "@radix-ui/react-avatar", replacement: path.resolve(__dirname, "./node_modules/@radix-ui/react-avatar") },
      { find: "@radix-ui/react-dropdown-menu", replacement: path.resolve(__dirname, "./node_modules/@radix-ui/react-dropdown-menu") },
      { find: "@radix-ui/react-separator", replacement: path.resolve(__dirname, "./node_modules/@radix-ui/react-separator") },
      { find: "@radix-ui/react-slot", replacement: path.resolve(__dirname, "./node_modules/@radix-ui/react-slot") },
      { find: "class-variance-authority", replacement: path.resolve(__dirname, "./node_modules/class-variance-authority") },
      { find: "clsx", replacement: path.resolve(__dirname, "./node_modules/clsx") },
      { find: "tailwind-merge", replacement: path.resolve(__dirname, "./node_modules/tailwind-merge") },
    ],
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
});
