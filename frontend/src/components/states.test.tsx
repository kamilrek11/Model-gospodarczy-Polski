import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { DisabledNotice } from "./DisabledNotice";
import { EmptyState } from "./EmptyState";
import { StatusBanner } from "./StatusBanner";

describe("StatusBanner", () => {
  it("StatusBanner shows last good data date on source error", () => {
    render(
      <StatusBanner
        error={null}
        status={{ state: "failed", errors: { gus_bdl: "timeout", nbp: "503" }, updated_at: "2026-10-09T12:00:00Z" }}
        updatedAt="2026-10-09T12:00:00Z"
        onRefresh={vi.fn()}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Ostatnie poprawne dane z 09.10.2026");
    expect(alert).toHaveTextContent("gus_bdl");
    expect(alert).toHaveTextContent("nbp");
    expect(screen.getByRole("button", { name: "Odśwież dane" })).toBeEnabled();
  });

  it("shows running state and disables the button", () => {
    render(<StatusBanner error={null} status={{ state: "running", errors: {}, updated_at: null }} updatedAt={null} onRefresh={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Odświeżanie…" })).toBeDisabled();
  });

  it("shows server error with last good date", () => {
    render(<StatusBanner error={new ApiError("server", "Błąd serwera (500)")} status={null} updatedAt="2026-10-09T12:00:00Z" onRefresh={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Błąd serwera (500)");
    expect(screen.getByRole("alert")).toHaveTextContent("09.10.2026");
  });

  it("renders identical warnings without React key collisions", () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <StatusBanner
        error={null}
        status={{ state: "done", errors: {}, warnings: ["mf_execution: 2015: x", "mf_execution: 2015: x"], updated_at: null }}
        updatedAt={null}
        onRefresh={vi.fn()}
      />,
    );
    expect(screen.getAllByText("mf_execution: 2015: x")).toHaveLength(2);
    expect(err.mock.calls.some((c) => String(c[0]).includes("same key"))).toBe(false);
    err.mockRestore();
  });

  it("lists source warnings of the last refresh without an error", () => {
    render(
      <StatusBanner
        error={null}
        status={{ state: "done", errors: {}, warnings: ["mf_execution: 2015: legacy .xls report is not supported"], updated_at: "2026-10-09T12:00:00Z" }}
        updatedAt="2026-10-09T12:00:00Z"
        onRefresh={vi.fn()}
      />,
    );
    const note = screen.getByRole("status");
    expect(note).toHaveTextContent("Uwagi do danych");
    expect(note).toHaveTextContent("mf_execution: 2015: legacy .xls report is not supported");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("refresh disabled in this instance: Polish notice instead of a generic error", () => {
    render(
      <StatusBanner
        error={null}
        status={{ state: "failed", errors: { refresh: "odświeżanie wyłączone w tej instancji" }, updated_at: null, disabled: true }}
        updatedAt={null}
        onRefresh={vi.fn()}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Odświeżanie wyłączone w tej instancji");
    expect(alert).not.toHaveTextContent("Nie udało się odświeżyć danych");
    expect(screen.getByRole("button", { name: "Odśwież dane" })).toBeDisabled();
  });

  it("renders nothing when all is well", () => {
    const { container } = render(<StatusBanner error={null} status={{ state: "idle", errors: {}, updated_at: null }} updatedAt={null} onRefresh={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("EmptyState", () => {
  it("explains and triggers refresh", async () => {
    const onRefresh = vi.fn();
    render(<EmptyState status={null} onRefresh={onRefresh} />);
    expect(screen.getByText(/Brak danych źródłowych/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Odśwież dane" }));
    expect(onRefresh).toHaveBeenCalled();
  });
});

describe("EmptyState with refresh disabled", () => {
  it("shows the Polish disabled message and a disabled button", () => {
    const onRefresh = vi.fn();
    render(<EmptyState status={{ state: "idle", errors: {}, updated_at: null, disabled: true }} onRefresh={onRefresh} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Odświeżanie wyłączone w tej instancji");
    expect(screen.getByRole("button", { name: "Odśwież dane" })).toBeDisabled();
    expect(screen.queryByText(/Odświeżenie nie powiodło się/)).toBeNull();
  });

  it("after a 403 (status failed + disabled) still shows the disabled message, not a generic failure", () => {
    render(<EmptyState status={{ state: "failed", errors: { refresh: "odświeżanie wyłączone w tej instancji" }, updated_at: null, disabled: true }} onRefresh={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Odświeżanie wyłączone w tej instancji");
    expect(screen.queryByText(/Odświeżenie nie powiodło się/)).toBeNull();
  });
});

describe("DisabledNotice", () => {
  it("disabled module notice rendered", () => {
    render(<DisabledNotice modules={[{ module: "cit", message: "Moduł CIT wyłączony: brak serii gross_surplus w danych." }]} />);
    expect(screen.getByRole("status")).toHaveTextContent("Moduł CIT wyłączony: brak serii gross_surplus w danych.");
  });
  it("renders nothing when empty", () => {
    const { container } = render(<DisabledNotice modules={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
