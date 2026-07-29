import axios, { AxiosError, type AxiosInstance } from "axios";
import { toast } from "sonner";
import { getToken } from "@/lib/auth-token";
import type { ApiError } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiHttpError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiHttpError";
  }
}

function createApiClient(): AxiosInstance {
  const client = axios.create({
    baseURL: API_URL,
    headers: { "Content-Type": "application/json" },
  });

  // Attach the app-issued JWT on every request
  client.interceptors.request.use((config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  // Normalise errors — preserve status code
  client.interceptors.response.use(
    (res) => res,
    (error: AxiosError<ApiError>) => {
      const status = error.response?.status ?? 0;

      // Rate-limit guard — surface a friendly toast so the user knows to slow down.
      if (status === 429) {
        toast.error("Too many requests — please slow down.");
        return Promise.reject(new ApiHttpError(429, "Too many requests — please slow down."));
      }

      const data = error.response?.data as (ApiError & { detail?: unknown }) | undefined;
      // FastAPI 422s return detail as [{loc, msg, type}] — join msg fields into one string.
      const detail = data?.detail;
      const detailStr = Array.isArray(detail)
        ? detail.map((d: { msg?: string }) => d.msg ?? String(d)).join("; ")
        : typeof detail === "string" ? detail : undefined;
      const message =
        data?.message ??
        detailStr ??
        error.message ??
        "An unexpected error occurred.";
      return Promise.reject(new ApiHttpError(status, message));
    }
  );

  return client;
}

export const api = createApiClient();
