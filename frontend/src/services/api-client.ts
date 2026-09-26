/**
 * Единый HTTP-клиент для FastAPI.
 *
 * VITE_API_BASE_URL должен содержать базовый URL API вместе с префиксом версии,
 * например: http://localhost:8000/api/v1.
 *
 * Аутентификация доставляется централизованно: auth-граница приложения один раз
 * регистрирует provider через setApiTokenProvider(), после чего каждый request()
 * сам добавляет заголовок Authorization: Bearer <token>. Токен нигде не хранится
 * и не логируется; при его отсутствии для запроса выбрасывается
 * ApiClientUnauthorizedError (fail-safe без запроса к backend).
 */

export interface ApiErrorPayload {
  detail?: string | Array<{ msg?: string }>;
}

export class ApiClientError extends Error {
  public readonly status: number;

  public constructor(message: string, status: number) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
  }
}

/** Отдельный тип ошибок аутентификации, чтобы auth-граница могла показать re-auth. */
export class ApiClientUnauthorizedError extends ApiClientError {
  public constructor(message = "Требуется повторная аутентификация.") {
    super(message, 401);
    this.name = "ApiClientUnauthorizedError";
  }
}

/** Возвращает актуальный session token или null, если активной сессии нет. */
type ApiTokenProvider = () => Promise<string | null>;

let apiTokenProvider: ApiTokenProvider | null = null;

/** Регистрирует центральный источник токена. Вызывается auth-границей приложения. */
export function setApiTokenProvider(provider: ApiTokenProvider | null): void {
  apiTokenProvider = provider;
}

function normalizeApiUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

function getApiUrl(): string {
  const apiUrl = import.meta.env.VITE_API_BASE_URL;

  if (!apiUrl) {
    throw new ApiClientError(
      "Не задана переменная окружения VITE_API_BASE_URL. Укажите URL FastAPI API, например http://localhost:8000/api/v1.",
      0,
    );
  }

  return normalizeApiUrl(apiUrl);
}

async function getErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as ApiErrorPayload;

    if (typeof payload.detail === "string") {
      return payload.detail;
    }

    if (Array.isArray(payload.detail)) {
      return payload.detail
        .map((item) => item.msg)
        .filter((message): message is string => Boolean(message))
        .join("; ");
    }
  } catch {
    // Ответ сервера может не содержать JSON с деталями ошибки.
  }

  return response.statusText || "Неизвестная ошибка API.";
}

/**
 * Формирует значение заголовка Authorization или null, если provider не зарегистрирован.
 * Если provider зарегистрирован, но токена нет — это защищённый запрос без сессии:
 * бросаем типизированную 401-ошибку, не выполняя заведомо неавторизованный запрос.
 */
async function resolveAuthorizationHeader(): Promise<string | null> {
  if (!apiTokenProvider) {
    return null;
  }

  let token: string | null;

  try {
    token = await apiTokenProvider();
  } catch {
    throw new ApiClientUnauthorizedError(
      "Не удалось получить токен сессии. Повторите вход.",
    );
  }

  if (!token) {
    throw new ApiClientUnauthorizedError();
  }

  return `Bearer ${token}`;
}

export class ApiClient {
  public async get<TResponse>(path: string): Promise<TResponse> {
    return this.request<TResponse>(path, { method: "GET" });
  }

  public async post<TResponse, TBody = undefined>(
    path: string,
    body?: TBody,
  ): Promise<TResponse> {
    return this.request<TResponse>(path, {
      method: "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  private async request<TResponse>(
    path: string,
    init: RequestInit,
  ): Promise<TResponse> {
    const headers: Record<string, string> = {
      Accept: "application/json",
      ...(init.headers as Record<string, string> | undefined),
    };

    const authorization = await resolveAuthorizationHeader();

    if (authorization) {
      headers.Authorization = authorization;
    }

    let response: Response;

    try {
      response = await fetch(`${getApiUrl()}${path}`, {
        ...init,
        headers,
      });
    } catch {
      throw new ApiClientError(
        "Не удалось подключиться к backend API. Проверьте VITE_API_BASE_URL и доступность FastAPI.",
        0,
      );
    }

    if (!response.ok) {
      const message = await getErrorMessage(response);

      if (response.status === 401) {
        throw new ApiClientUnauthorizedError(message);
      }

      throw new ApiClientError(message, response.status);
    }

    return (await response.json()) as TResponse;
  }
}

export const apiClient = new ApiClient();
