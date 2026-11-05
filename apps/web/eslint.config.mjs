import { defineConfig, globalIgnores } from "eslint/config";
import js from "@eslint/js";
import ts from "typescript-eslint";
import globals from "globals";
import hooks from "eslint-plugin-react-hooks";
import next from "@next/eslint-plugin-next";
export default defineConfig([
  globalIgnores([".next/**", "node_modules/**", "next-env.d.ts"]),
  js.configs.recommended,
  ...ts.configs.recommended,
  { languageOptions: { globals: { ...globals.browser, ...globals.node } } },
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { "react-hooks": hooks, "@next/next": next },
    rules: {
      ...hooks.configs.recommended.rules,
      ...next.configs.recommended.rules,
      ...next.configs["core-web-vitals"].rules,
    },
  },
]);
