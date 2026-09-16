export const percent = (value: number | null) => value === null ? "—" : `${(value * 100).toFixed(1)}%`;
export const money = (value: number) => value.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
export const label = (value: string) => value.replace(/_/g, " ").toLowerCase();
export const clock = (minutes: number) => `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(Math.floor(minutes % 60)).padStart(2, "0")}`;
