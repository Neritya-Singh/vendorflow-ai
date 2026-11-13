import { render, screen } from "@testing-library/react";
import { api } from "../../lib/api";
import type { FixView } from "../../lib/types";
import { AppStateProvider } from "../../state";
import { FixPanel } from "./FixPanel";

const field = (key: string, label: string, document: "GST" | "BANK", value: string) =>
  ({ key, label, document, value, document_value: value, status: "document", error: null });

const view = {
  application_id: "VF-0123456789AB", owner: "VENDOR", buyer: "Zamp AI", rev: 1,
  files: {
    GST: { filename: "gst.pdf", status: "read", message: "Read: legal name", suggested_slot: null, pages: 1, uploaded_at: null, on_file: true },
    BANK: { filename: "old_cheque.pdf", status: "read", message: "Read: account holder", suggested_slot: null, pages: 1, uploaded_at: null, on_file: true },
  },
  fields: [field("legal_name", "Legal name", "GST", "SAMPLE Steelworks"), field("ifsc", "IFSC", "BANK", "DEMO0123456")],
  pan: { value: "", source: "GSTIN" }, address: null,
  contact: { name: "A", email: "a@example.com", phone: "+91 98765 43210" }, contact_errors: {},
  declaration: true, documents_ready: true, details_ready: true, blockers: ["Upload a new bank document."], flagged: [],
  items: [{ id: "doc:BANK", kind: "document", slot: "BANK", text: "Upload a new bank document." }],
  show_slots: ["BANK"], shown_fields: [], show_contact: false, ready: false,
} as unknown as FixView;

describe("FixPanel", () => {
  beforeEach(() => {
    vi.spyOn(api, "health").mockResolvedValue({} as never);
    vi.spyOn(api, "meta").mockResolvedValue({ states: [], max_pdf_bytes: 5 * 1024 * 1024, stages: [] } as never);
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows only the requested document slot, never the full form", async () => {
    vi.spyOn(api, "openFix").mockResolvedValue(view);
    render(<AppStateProvider><FixPanel creds={{ application_id: "VF-0123456789AB", tracking_code: "x".repeat(24) }} onSaved={() => {}} /></AppStateProvider>);
    expect(await screen.findByText("On file now: old_cheque.pdf. Upload a new one.")).toBeInTheDocument();
    expect(screen.getByText("Cancelled cheque or bank letter")).toBeInTheDocument();
    expect(screen.queryByText("GST registration certificate")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Legal name")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Contact name")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-check" })).toBeDisabled();
  });

  it("shows a requested field with its input and enables re-check when ready", async () => {
    vi.spyOn(api, "openFix").mockResolvedValue({
      ...view, items: [{ id: "field:ifsc", kind: "field", field: "ifsc", text: "Check your IFSC." }],
      show_slots: [], shown_fields: ["ifsc"], ready: true, blockers: [],
    } as FixView);
    render(<AppStateProvider><FixPanel creds={{ application_id: "VF-0123456789AB", tracking_code: "x".repeat(24) }} onSaved={() => {}} /></AppStateProvider>);
    expect(await screen.findByLabelText("IFSC")).toHaveValue("DEMO0123456");
    expect(screen.queryByLabelText("Legal name")).not.toBeInTheDocument();
    expect(screen.queryByText("Cancelled cheque or bank letter")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-check" })).toBeEnabled();
  });
});
