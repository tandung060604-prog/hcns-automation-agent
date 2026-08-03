interface ImportMetaEnv {
  readonly VITE_SHOW_HELDOUT?: string;
  readonly VITE_SHOW_GROUND_TRUTH_REVIEW?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
