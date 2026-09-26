import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ClerkProvider } from "@clerk/react";
import AuthGate from "./components/AuthGate";
import "./index.css";

// Publishable key — публичное значение, но реальный ключ в репозиторий не коммитим:
// он задаётся через .env frontend (см. frontend/.env.example).
const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

if (!publishableKey) {
  throw new Error(
    "Не задана переменная окружения VITE_CLERK_PUBLISHABLE_KEY. Добавьте publishable key Clerk в .env frontend.",
  );
}

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Не найден корневой элемент приложения.");
}

createRoot(rootElement).render(
  <StrictMode>
    <ClerkProvider
      publishableKey={publishableKey}
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      signInFallbackRedirectUrl="/"
      signUpFallbackRedirectUrl="/"
    >
      <AuthGate />
    </ClerkProvider>
  </StrictMode>
);
