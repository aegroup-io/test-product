import { StrictMode } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { LocaleProvider } from "./lib/locale-context";
import { ThemeProvider } from "./lib/theme-context";
import "./styles.css";

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
