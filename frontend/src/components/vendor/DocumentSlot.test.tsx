import { fireEvent, render, screen } from "@testing-library/react";
import { DocumentSlot } from "./DocumentSlot";

const noop = () => {};

describe("DocumentSlot", () => {
  it("warns about a file in the wrong slot and offers to move it", () => {
    const onMove = vi.fn();
    render(
      <DocumentSlot
        slot="GST"
        file={{ filename: "cheque.pdf", status: "wrong_slot", suggested_slot: "BANK", pages: 1, uploaded_at: null,
          message: "This looks like a bank document. Did you mean to put it in the bank slot?" }}
        activity={null} error={null} maxBytes={5 * 1024 * 1024} onFile={noop} onMove={onMove} onRetry={null}
      />,
    );
    expect(screen.getByText(/Did you mean to put it in the bank slot\?/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Move it" }));
    expect(onMove).toHaveBeenCalledOnce();
  });

  it("shows the live reading stage, then offers the camera for a photo", () => {
    const { rerender } = render(
      <DocumentSlot slot="BANK" file={null} activity={{ filename: "letter.pdf", stage: "Reading the details", progress: 80 }}
        error={null} maxBytes={1} onFile={noop} onMove={noop} onRetry={null} />,
    );
    expect(screen.getByText("letter.pdf · Reading the details…")).toBeInTheDocument();
    rerender(<DocumentSlot slot="BANK" file={null} activity={null} error={null} maxBytes={1} onFile={noop} onMove={noop} onRetry={null} />);
    const take = screen.getByRole("button", { name: "Take photo of your bank document" });
    expect(take).toBeEnabled();
    expect(screen.queryByText(/supported soon/)).not.toBeInTheDocument();
    const cameraInput = document.querySelector('input[data-camera="BANK"]')!;
    expect(cameraInput).toHaveAttribute("capture", "environment");
    expect(cameraInput).toHaveAttribute("accept", "image/*");
    expect(screen.getByLabelText("Cancelled cheque or bank letter file")).toHaveAttribute("accept", expect.stringContaining("image/jpeg"));
  });
});
