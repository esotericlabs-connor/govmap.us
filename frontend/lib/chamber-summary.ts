import type { ChamberBalance, ChamberSummary } from "./api";

function isBalance(value: unknown): value is ChamberBalance {
  if (typeof value !== "object" || value === null ||
    !("D" in value) || !("R" in value) || !("I" in value) || !("total" in value)) return false;
  const counts = [value.D, value.R, value.I, value.total];
  if (!counts.every((count) => typeof count === "number" && Number.isSafeInteger(count) && count >= 0)) {
    return false;
  }
  // Bound generated seat geometry as well as validating the response shape.
  return typeof value.D === "number" && typeof value.R === "number" &&
    typeof value.I === "number" && typeof value.total === "number" &&
    value.total <= 1000 && value.D + value.R + value.I <= value.total;
}

export function parseChamberSummary(value: unknown): ChamberSummary {
  if (typeof value !== "object" || value === null ||
    !("house" in value) || !("senate" in value) ||
    !isBalance(value.house) || !isBalance(value.senate)) {
    throw new Error("Chamber summary contains invalid seat counts.");
  }
  return { house: value.house, senate: value.senate };
}
