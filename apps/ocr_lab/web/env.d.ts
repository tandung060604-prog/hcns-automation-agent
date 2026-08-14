interface ImportMetaEnv {
  readonly VITE_ADVANCED_DIAGNOSTICS?: string;
  readonly VITE_SHOW_GROUND_TRUTH_REVIEW?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
