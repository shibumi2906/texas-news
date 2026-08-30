import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "./page";

describe("Home", () => {
  it("renders the Phase 0 application shell", () => {
    render(<Home />);

    expect(
      screen.getByRole("heading", {
        name: "Local Entertainment News Platform",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("The web application foundation is running."),
    ).toBeInTheDocument();
  });
});
