/**
 * The skeleton page exists so the lane has something real to lint, typecheck and render. It is
 * replaced wholesale by the accounts table in OME-708; what this test protects until then is that
 * the app renders at all under the configured jsdom + React 19 setup.
 */
import { render, screen } from "@testing-library/react";

import Page from "./page";

describe("the admin console shell", () => {
  it("names itself in a top-level heading", () => {
    render(<Page />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/aigateway admin/i);
  });
});
