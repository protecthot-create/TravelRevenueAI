/**
 * Единый HTTP-клиент для FastAPI.
 *
 * VITE_API_URL должен содержать базовый URL API вместе с префиксом версии,
 * например: http://localhost:8000/api/v1.
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

function normalizeApiUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

function getApiUrl(): string {
  const apiUrl = import.meta.env.VITE_API_URL;

  if (!apiUrl) {
    throw new ApiClientError(
      "Не задана переменная окружения VITE_API_URL. Укажите URL FastAPI API, например http://localhost:8000/api/v1.",
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

export class ApiClient {
  public async get<TResponse>(path: string): Promise<TResponse> {
    return this.request<TResponse>(path, { method: "GET" });
  }

  public async post<TResponse, TBody>(
    path: string,
    body: TBody,
  ): Promise<TResponse> {
    return this.request<TResponse>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  private async request<TResponse>(
    path: string,
    init: RequestInit,
  ): Promise<TResponse> {
    let response: Response;

    try {
      response = await fetch(`${getApiUrl()}${path}`, {
        ...init,
        headers: {
          Accept: "application/json",
          ...init.headers,
        },
      });
    } catch {
      throw new ApiClientError(
        "Не удалось подключиться к backend API. Проверьте VITE_API_URL и доступность FastAPI.",
        0,
      );
    }

    if (!response.ok) {
      throw new ApiClientError(
        await getErrorMessage(response),
        response.status,
      );
    }

    return (await response.json()) as TResponse;
  }
}

export const apiClient = new ApiClient();