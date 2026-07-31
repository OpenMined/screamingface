/**
 * The primitives carry the console's accessibility contract, so that is what is asserted here:
 * a label that actually points at its control, an error a screen reader will reach, semantic
 * table markup. Appearance is the stylesheet's job and is not tested.
 */
import { render, screen } from "@testing-library/react";

import {
  Badge,
  Button,
  EmptyState,
  Field,
  Input,
  Notice,
  Select,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
  Textarea,
} from "./ui";

describe("Button", () => {
  it("renders its label and defaults to the primary variant", () => {
    render(<Button>Provision tenant</Button>);

    const button = screen.getByRole("button", { name: "Provision tenant" });
    expect(button).toHaveClass("ui-btn", "ui-btn-primary");
  });

  it("carries the requested variant and keeps a caller's own class", () => {
    render(
      <Button variant="danger" className="pull-right">
        Detach key
      </Button>,
    );

    expect(screen.getByRole("button", { name: "Detach key" })).toHaveClass(
      "ui-btn",
      "ui-btn-danger",
      "pull-right",
    );
  });

  it("forwards native button props rather than swallowing them", () => {
    render(
      <Button variant="ghost" type="submit" disabled>
        Save
      </Button>,
    );

    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("type", "submit");
  });
});

describe("Field", () => {
  it("associates the label with the control by deriving an id from its name", () => {
    render(
      <Field label="Email address">
        <Input name="email" />
      </Field>,
    );

    const control = screen.getByLabelText("Email address");
    expect(control).toHaveAttribute("id", "field-email");
    expect(control).toHaveClass("ui-control", "ui-input");
  });

  it("prefers an id the control already carries", () => {
    render(
      <Field label="Display name">
        <Input id="chosen" name="display_name" />
      </Field>,
    );

    expect(screen.getByLabelText("Display name")).toHaveAttribute("id", "chosen");
  });

  it("falls back to the label text when the control has neither id nor name", () => {
    render(
      <Field label="Provider key">
        <Input type="password" />
      </Field>,
    );

    expect(screen.getByLabelText("Provider key")).toHaveAttribute("id", "field-provider-key");
  });

  it("exposes the error through aria-describedby and marks the control invalid", () => {
    render(
      <Field label="Email address" error="That address is already provisioned.">
        <Input name="email" />
      </Field>,
    );

    const control = screen.getByLabelText("Email address");
    expect(control).toHaveAttribute("aria-invalid", "true");
    expect(control).toHaveAccessibleDescription("That address is already provisioned.");
    expect(screen.getByRole("alert")).toHaveTextContent("That address is already provisioned.");
  });

  it("describes the control with the hint, and with both when an error joins it", () => {
    const { rerender } = render(
      <Field label="Model" hint="Applied when the request omits one.">
        <Input name="model" />
      </Field>,
    );

    expect(screen.getByLabelText("Model")).toHaveAccessibleDescription(
      "Applied when the request omits one.",
    );
    expect(screen.getByLabelText("Model")).not.toHaveAttribute("aria-invalid");

    rerender(
      <Field label="Model" hint="Applied when the request omits one." error="Unknown model.">
        <Input name="model" />
      </Field>,
    );

    expect(screen.getByLabelText("Model")).toHaveAccessibleDescription(
      "Applied when the request omits one. Unknown model.",
    );
  });

  it("wires a select or a textarea the same way", () => {
    render(
      <>
        <Field label="Provider">
          <Select name="provider">
            <option value="openai">openai</option>
          </Select>
        </Field>
        <Field label="System prompt">
          <Textarea name="system_prompt" />
        </Field>
      </>,
    );

    expect(screen.getByLabelText("Provider")).toHaveAttribute("id", "field-provider");
    expect(screen.getByLabelText("System prompt")).toHaveClass("ui-control", "ui-textarea");
  });

  it("leaves non-element children alone and binds only the first control", () => {
    render(
      <Field label="Max tokens" htmlFor="explicit">
        Budget:
        <Input id="explicit" name="max_tokens" />
        <Input name="second" />
      </Field>,
    );

    expect(screen.getByLabelText("Max tokens")).toHaveAttribute("name", "max_tokens");
    expect(screen.getByLabelText("Max tokens").closest(".ui-field")).toHaveTextContent("Budget:");

    const controls = screen.getAllByRole("textbox");
    expect(controls).toHaveLength(2);
    expect(controls[1]).toHaveAttribute("name", "second");
    expect(controls[1]).not.toHaveAttribute("id");
  });
});

describe("Notice", () => {
  it("renders its tone as a class and as data-tone", () => {
    render(
      <Notice tone="success" title="Key attached">
        The tenant can call the gateway now.
      </Notice>,
    );

    const notice = screen.getByRole("status");
    expect(notice).toHaveClass("ui-notice", "ui-notice-success");
    expect(notice).toHaveAttribute("data-tone", "success");
    expect(notice).toHaveTextContent("Key attached");
    expect(notice).toHaveTextContent("The tenant can call the gateway now.");
  });

  it("announces an error tone assertively", () => {
    render(<Notice tone="error">The gateway refused the key.</Notice>);

    const notice = screen.getByRole("alert");
    expect(notice).toHaveClass("ui-notice-error");
    expect(notice).toHaveAttribute("data-tone", "error");
  });

  it("renders the info tone without a title", () => {
    render(<Notice tone="info">Nothing has changed yet.</Notice>);

    expect(screen.getByRole("status")).toHaveClass("ui-notice-info");
  });
});

describe("EmptyState", () => {
  it("renders its title and message", () => {
    render(<EmptyState title="No tenants yet" message="Provision one to get started." />);

    expect(screen.getByText("No tenants yet")).toBeInTheDocument();
    expect(screen.getByText("Provision one to get started.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders the action when one is given", () => {
    render(
      <EmptyState
        title="No credentials"
        message="Attach a provider API key."
        action={<Button>Attach a key</Button>}
      />,
    );

    expect(screen.getByRole("button", { name: "Attach a key" })).toBeInTheDocument();
  });
});

describe("Badge", () => {
  it("defaults to the neutral tone and states its meaning in text", () => {
    render(<Badge>pending</Badge>);

    const badge = screen.getByText("pending");
    expect(badge).toHaveClass("ui-badge", "ui-badge-neutral");
    expect(badge).toHaveAttribute("data-tone", "neutral");
  });

  it.each([
    ["good", "active"],
    ["bad", "suspended"],
  ] as const)("renders the %s tone", (tone, label) => {
    render(<Badge tone={tone}>{label}</Badge>);

    expect(screen.getByText(label)).toHaveClass(`ui-badge-${tone}`);
  });
});

describe("Table", () => {
  it("renders semantic markup with column-scoped headers", () => {
    render(
      <Table>
        <THead>
          <TR>
            <TH>Tenant</TH>
            <TH>State</TH>
          </TR>
        </THead>
        <TBody>
          <TR>
            <TH scope="row">ada@example.org</TH>
            <TD>active</TD>
          </TR>
        </TBody>
      </Table>,
    );

    expect(screen.getByRole("table")).toHaveClass("ui-table");
    expect(screen.getByRole("columnheader", { name: "Tenant" })).toHaveAttribute("scope", "col");
    expect(screen.getByRole("rowheader", { name: "ada@example.org" })).toHaveAttribute(
      "scope",
      "row",
    );
    expect(screen.getByRole("cell", { name: "active" })).toHaveClass("ui-td");
  });
});
