import { render, screen } from "@testing-library/react";
import { DecisionCard } from "./Outcome";
import type { VendorView } from "../lib/types";

const base: VendorView = {
  application_id: "VF-0123456789AB", status: "PENDING", status_label: "Pending Review", decision_source: "AUTOMATED",
  owner: "Technical retry", processing_unavailable: true, heading: "Retry the document check",
  next_step: "Retry below.", reasons: ["Document processing was temporarily unavailable."], reviewer_note: null,
  checks: [], stages: [], elapsed_ms: 10, timeline: [], documents: [], editable: true, needs_resume: false,
  latest_run_id: "RUN-0123456789AB", submitted: {}, created_at: null,
};

describe("DecisionCard", () => {
  it("states an outage truthfully instead of blaming the documents", () => {
    render(<DecisionCard view={base} />);
    expect(screen.getByRole("heading", { name: "Pending Review" })).toBeInTheDocument();
    expect(screen.getByText("Document processing temporarily unavailable")).toBeInTheDocument();
    expect(screen.queryByText(/unreadable/i)).not.toBeInTheDocument();
  });

  it("shows a reviewer's rejection reason", () => {
    render(
      <DecisionCard
        view={{ ...base, status: "REJECTED", processing_unavailable: false, owner: "Complete", decision_source: "MANUAL",
          reviewer_note: { action: "REJECT", title: "Rejected by reviewer", message: "Account belongs to an individual.", at: null } }}
      />,
    );
    expect(screen.getByRole("heading", { name: "Rejected" })).toBeInTheDocument();
    expect(screen.getByText(/Account belongs to an individual/)).toBeInTheDocument();
  });
});
