import type { Band, HistoryData, SimulationResult } from "./api/types";

function band(median: number[]): Band {
  return {
    median,
    p10: median.map((v) => v - 3),
    p90: median.map((v) => v + 3),
    p2_5: median.map((v) => v - 5),
    p97_5: median.map((v) => v + 5),
  };
}

export const history: HistoryData = {
  pit: [
    { year: 2023, value: 90 },
    { year: 2024, value: 95 },
    { year: 2025, value: 100 },
  ],
  cit: [
    { year: 2023, value: 60 },
    { year: 2024, value: 62 },
    { year: 2025, value: 64 },
  ],
  vat: [
    { year: 2023, value: 280 },
    { year: 2024, value: 290 },
    { year: 2025, value: 300 },
  ],
};

export const sim: SimulationResult = {
  years: [2026, 2027],
  taxes: {
    pit: band([100, 110.5]),
    cit: band([65, 66]),
    vat: band([310, 320]),
  },
  baseline: {
    pit: { median: [100, 108] },
    cit: { median: [65, 66] },
    vat: { median: [310, 320] },
    total: { median: [475, 494] },
  },
  total: band([475, 496.5]),
  macro: {},
  calibration: {},
  assumptions: [],
  disabled_modules: [],
  model_version: "test",
  data_updated_at: "2026-10-09T12:00:00Z",
};
