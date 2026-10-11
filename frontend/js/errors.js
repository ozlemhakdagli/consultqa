// The client's error type and the Turkish text of every error code the page can show.
import { has, t } from "./i18n.js";

export class ApiError extends Error {
  constructor(code, status = 0, body = {}) {
    super(code);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.body = body;
  }
}

export function errorMessage(code) {
  return has(`error.${code}`) ? t(`error.${code}`) : t("error.unknown");
}
