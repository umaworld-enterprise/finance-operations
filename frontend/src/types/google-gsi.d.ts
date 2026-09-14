// Minimal typings for the Google Identity Services auth-code popup flow.
// https://developers.google.com/identity/oauth2/web/reference/js-reference

interface GoogleCodeResponse {
  code?: string;
  error?: string;
  error_description?: string;
}

interface GoogleCodeClient {
  requestCode: () => void;
}

interface GoogleCodeClientConfig {
  client_id: string;
  scope: string;
  ux_mode: "popup" | "redirect";
  callback: (response: GoogleCodeResponse) => void;
  error_callback?: (error: { type: string; message?: string }) => void;
}

interface Window {
  google?: {
    accounts?: {
      oauth2?: {
        initCodeClient: (config: GoogleCodeClientConfig) => GoogleCodeClient;
      };
    };
  };
}
