import { StrictMode } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { LocaleProvider, ThemeProvider } from "@aegroup/agent-core-web-shell";
import "@aegroup/agent-core-web-shell/styles.css";

import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <LocaleProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </LocaleProvider>
    </ThemeProvider>
  </StrictMode>,
);
