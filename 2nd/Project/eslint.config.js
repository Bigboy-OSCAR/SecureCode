// ESLint flat config for every TypeScript package (task 3.2). Rules are explained in
// docs/conventions/TYPESCRIPT_REACT.md.
import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

const sdkImportRestriction = {
    paths: [],
    patterns: [
        {
            group: ["@cline/*"],
            message: "Import the Cline SDK only under apps/host/src/cline/ (adapter boundary) or the probe.",
        },
    ],
};

export default tseslint.config(
    {
        ignores: ["**/node_modules/**", "**/dist/**", "**/coverage/**", ".securecode/**", "contracts/generated/**"],
    },
    js.configs.recommended,
    {
        files: ["**/*.ts"],
        extends: [...tseslint.configs.recommendedTypeChecked],
        languageOptions: {
            globals: { ...globals.node },
            parserOptions: {
                projectService: true,
                tsconfigRootDir: import.meta.dirname,
            },
        },
        rules: {
            eqeqeq: ["error", "always"],
            "@typescript-eslint/no-explicit-any": "error",
            "@typescript-eslint/no-floating-promises": [
                "error",
                {
                    allowForKnownSafeCalls: [
                        { from: "package", package: "node:test", name: ["describe", "it", "test", "before", "after"] },
                    ],
                },
            ],
            // Interface methods (SDK hooks, ports) must return Promise even when the body is synchronous.
            "@typescript-eslint/require-await": "off",
            "@typescript-eslint/no-misused-promises": "error",
            "@typescript-eslint/explicit-module-boundary-types": "error",
            "@typescript-eslint/consistent-type-imports": "error",
            "@typescript-eslint/switch-exhaustiveness-check": "error",
            "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
            "@typescript-eslint/naming-convention": [
                "error",
                { selector: "default", format: ["camelCase"], leadingUnderscore: "allow" },
                { selector: "variable", format: ["camelCase", "UPPER_CASE"] },
                { selector: "function", format: ["camelCase"] },
                { selector: "typeLike", format: ["PascalCase"] },
                { selector: "enumMember", format: ["PascalCase"] },
                // JSON wire fields stay snake_case (roadmap 0.5); mapping happens in one mapper.
                { selector: ["objectLiteralProperty", "typeProperty"], format: null },
                { selector: "import", format: null },
            ],
        },
    },
    {
        files: ["apps/host/src/**/*.ts"],
        ignores: ["apps/host/src/cline/**"],
        rules: {
            "no-restricted-imports": ["error", sdkImportRestriction],
            "no-console": "error",
        },
    },
    {
        files: ["contracts/**/*.ts", "scripts/**/*.ts"],
        rules: {
            "no-restricted-imports": ["error", sdkImportRestriction],
        },
    },
    {
        files: ["**/*.js"],
        languageOptions: { globals: { ...globals.node } },
    },
);
