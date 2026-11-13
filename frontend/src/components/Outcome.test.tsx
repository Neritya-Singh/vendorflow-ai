import { render, screen } from "@testing-library/react";
import { DecisionCard } from "./Outcome";
import type { VendorView } from "../lib/types";

const base: VendorView = {
  application_id: "VF-0123456789AB", status: "PENDING", status_label: "With our team", decision_source: "AUTOMATED",
  owner: "TEAM", processing_unavailable: true, retry_available: true, heading: "With our team — no action needed",
  next_step: "Our team will look at it.", reasons: ["We couldn't read your documents just now because of a temporary problem on our side."],
  todo: [], reviewer_note: null, stages: [], elapsed_ms: 10, timeline: [], documents: [], editable: false, needs_resume: false,
  latest_run_id: "RUN-0123456789AB", submitted: {}, created_at: null,
};

describe("DecisionCard", () => {
  it("says the team acts next and blames nothing on the vendor during an outage", () => {
    render(<DecisionCard view={base} />);
    expect(screen.getByRole("heading", { name: "With our team — no action needed" })).toBeInTheDocument();
    expect(screen.getByText(/temporary problem on our side/)).toBeInTheDocument();
    expect(screen.queryByText(/What we need from you/)).not.toBeInTheDocument();
  });

  it("lists exactly what the vendor must fix", () => {
    render(
      <DecisionCard
        view={{ ...base, owner: "VENDOR", status_label: "Action needed from you", heading: "Action needed from you",
          reasons: ["We need 2 things before we can continue."], editable: true, retry_available: false,
          todo: [{ key: "swapped", text: "Your files look swapped." }, { key: "R07", text: "Check your IFSC." }] }}
      />,
    );
    expect(screen.getByText("What we need from you (2 items)")).toBeInTheDocument();
    expect(screen.getByText("Your files look swapped.")).toBeInTheDocument();
  });

  it("shows a reviewer's rejection reason", () => {
    render(
      <DecisionCard
        view={{ ...base, status: "REJECTED", status_label: "Not approved", heading: "Not approved", owner: "COMPLETE",
          decision_source: "MANUAL", retry_available: false,
          reasons: ["We couldn't approve your application: Account belongs to an individual."],
          reviewer_note: { action: "REJECT", title: "Not approved by our team", message: "Account belongs to an individual.", at: null } }}
      />,
    );
    expect(screen.getByRole("heading", { name: "Not approved" })).toBeInTheDocument();
    expect(screen.getByText(/Account belongs to an individual/)).toBeInTheDocument();
  });
});
