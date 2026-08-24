/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the `api` service, e.g. http://localhost:8000. Set at build
   *  time via docker-compose.yml's `VITE_API_BASE_URL` build arg. */
  readonly VITE_API_BASE_URL?: string;
  /** When "true", installs the hand-rolled fetch mock so the app runs
   *  end-to-end in dev mode without the `api` service. See src/mocks/. */
  readonly VITE_USE_MOCKS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
