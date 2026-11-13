import { fireEvent, render, screen } from "@testing-library/react";
import { DecisionDialog, vendorPreview } from "./DecisionDialog";
import type { AdminCase } from "../../lib/types";

const c = {
  application_id: "VF-0123456789AB", business: "SAMPLE Steelworks", revision: 1, latest_run_id: "RUN-0123456789AB",
  correction_draft: "Upload a recent letter from your bank.", requires_confirmation: true,
  confirmation_text: "Bank change confirmed by call-back to the contact on the existing record",
  correction_items: [{ id: "doc:GST", label: "New GST certificate" }, { id: "doc:BANK", label: "New bank document" }, { id: "field:ifsc", label: "IFSC" }],
  suggested_items: ["doc:BANK"],
} as unknown as AdminCase;
const noop = () => {};

describe("DecisionDialog", () => {
  it("pre-drafts the correction message and previews the vendor text", () => {
    render(<DecisionDialog c={c} action="REQUEST_CORRECTION" onClose={noop} onSaved={noop} onUnauthorized={() => false} />);
    expect(screen.getByLabelText("Message to the vendor")).toHaveValue("Upload a recent letter from your bank.");
    expect(screen.getByText("Our team needs one change: Upload a recent letter from your bank. Open your application page to make it.")).toBeInTheDocument();
  });

  it("blocks approval of a matched case until the call-back confirmation is ticked", () => {
    render(<DecisionDialog c={c} action="APPROVE" onClose={noop} onSaved={noop} onUnauthorized={() => false} />);
    const approve = screen.getByRole("button", { name: "Approve" });
    fireEvent.click(screen.getByRole("button", { name: "Documents consistent after manual check" }));
    expect(approve).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/Bank change confirmed by call-back/));
    expect(approve).toBeEnabled();
  });

  it("requires a reason to reject", () => {
    render(<DecisionDialog c={{ ...c, requires_confirmation: false }} action="REJECT" onClose={noop} onSaved={noop} onUnauthorized={() => false} />);
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    expect(vendorPreview("REJECT", "Bank account not owned by the business.")).toBe(
      "We couldn't approve your application: Bank account not owned by the business. Questions: contact Zamp AI's finance team.",
    );
  });

  it("pre-selects the flagged items for a correction and needs at least one", () => {
    render(<DecisionDialog c={c} action="REQUEST_CORRECTION" onClose={noop} onSaved={noop} onUnauthorized={() => false} />);
    const bank = screen.getByRole("button", { name: "New bank document" });
    expect(bank).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "IFSC" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Send request" })).toBeEnabled();
    fireEvent.click(bank);
    expect(screen.getByRole("button", { name: "Send request" })).toBeDisabled();
    expect(screen.getByText("Choose at least one item.")).toBeInTheDocument();
  });
});
