import React from "react";
import { createRoot } from "react-dom/client";
import { App, approval } from "./app";
const token = approval.approvalToken();
createRoot(document.getElementById("root")).render(
  token ? <approval.ApprovalPage token={token} /> : <App />,
);
