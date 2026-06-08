import type { Payload } from "../types";
import type { BridgeSource } from "../adapters/bridge";
import { render } from "../renderer";
import { el } from "../dom";

type ListProjectsResult = {
    projects: Array<{ path: string; name: string }>;
    current?: string;
};

export function bootDashboard(root: HTMLElement, source: BridgeSource): void {
    // ---- Brand cmd (always "dashboard") ----
    const brandCmd = document.getElementById("brand-cmd");
    if (brandCmd) brandCmd.textContent = "dashboard";

    // ---- Header additions: project-info + mode-pill ----
    const headerInner = document.querySelector<HTMLElement>(".site-header-inner");
    const projectInfo = el("div", { class: "db-project-info" });
    const modePill = el("span", { class: "db-mode-pill" }, "live");
    if (headerInner) headerInner.append(projectInfo, modePill);

    // ---- Toolbar (between header and main) ----
    const toolbar = el("div", { class: "db-toolbar" });
    const projectSelect = el("select", { class: "db-project-select" }) as HTMLSelectElement;
    const btnScan = el("button", { class: "primary" }, "Scan") as HTMLButtonElement;
    const btnChecks = el("button", {}, "Run checks") as HTMLButtonElement;
    const btnDoc = el("button", {}, "Doc") as HTMLButtonElement;
    const btnDepends = el("button", {}, "Depends") as HTMLButtonElement;
    const btnRelease = el("button", {}, "Release") as HTMLButtonElement;
    btnScan.disabled = btnChecks.disabled = btnDoc.disabled = btnDepends.disabled = btnRelease.disabled = true;
    toolbar.append(projectSelect, btnScan, btnChecks, btnDoc, btnDepends, btnRelease);
    root.insertAdjacentElement("beforebegin", toolbar);

    // ---- Helpers ----
    function showLoading(label: string) {
        root.innerHTML = "";
        root.append(
            el("div", { class: "db-loading" }, [el("div", { class: "db-spinner" }), el("span", {}, label + "…")]),
        );
    }

    function showError(msg: string) {
        root.innerHTML = "";
        root.append(el("div", { class: "db-error" }, [el("strong", {}, "Error: "), document.createTextNode(msg)]));
    }

    function setButtons(on: boolean) {
        btnScan.disabled = btnChecks.disabled = btnDoc.disabled = btnDepends.disabled = btnRelease.disabled = !on;
    }

    function renderProjectInfo(payload: Payload) {
        projectInfo.innerHTML = "";
        const meta = (payload as Record<string, unknown>)["metadata"] as Record<string, unknown> | undefined;
        const groups = (payload as Record<string, unknown>)["metrics"] as
            | Array<{ label: string; values: Array<{ name: string; value: unknown }> }>
            | undefined;
        const odoo = groups?.find((g) => g.label === "odoo")?.values ?? [];
        const pick = (name: string) => String(odoo.find((v) => v.name === name)?.value ?? "—");
        const pairs: [string, string][] = [
            ["Project", String(meta?.["project_name"] ?? "—")],
            ["Odoo", pick("Version")],
            ["Branch", String(meta?.["git_branch"] ?? "—")],
        ];
        pairs
            .filter(([, v]) => v !== "—")
            .forEach(([k, v]) =>
                projectInfo.append(
                    el("div", { class: "db-pi" }, [
                        el("span", { class: "db-pi-k" }, k),
                        el("span", { class: "db-pi-v" }, v),
                    ]),
                ),
            );
    }

    function renderInApp(payload: Payload) {
        render(root, payload, source);
        // Keep brand-cmd as "dashboard" regardless of payload.metadata.command.
        if (brandCmd) brandCmd.textContent = "dashboard";
    }

    async function runCommand(method: string, label: string, ...args: unknown[]) {
        showLoading(label);
        setButtons(false);
        try {
            renderInApp(await source.run(method, ...args));
        } catch (e) {
            showError((e as Error).message);
        } finally {
            setButtons(true);
        }
    }

    btnScan.addEventListener("click", () => void runCommand("scan_project", "Scanning project"));
    btnChecks.addEventListener("click", () => void runCommand("check_all", "Running checks"));
    btnDoc.addEventListener("click", () => void runCommand("doc_project", "Building docs"));
    btnDepends.addEventListener("click", () => void runCommand("show_depends", "Calculating dependencies"));
    btnRelease.addEventListener("click", () => void runCommand("show_release", "Retrieving releases"));

    projectSelect.addEventListener("change", async () => {
        await source.run("select_project", projectSelect.value);
        void loadProject();
    });

    async function loadProject() {
        showLoading("Scanning project");
        setButtons(false);
        try {
            const payload = await source.run("scan_project");
            renderProjectInfo(payload);
            renderInApp(payload);
        } catch (e) {
            showError((e as Error).message);
        } finally {
            setButtons(true);
        }
    }

    async function init() {
        showLoading("Connecting…");
        try {
            const raw = (await source.run("list_projects")) as unknown as ListProjectsResult;
            const projects = raw.projects ?? [];
            projectSelect.innerHTML = "";
            projects.forEach((pr) => {
                const o = el("option", { value: pr.path }, pr.name) as HTMLOptionElement;
                if (pr.path === raw.current) o.selected = true;
                projectSelect.append(o);
            });
            if (projects.length) {
                await source.run("select_project", projectSelect.value);
                void loadProject();
            } else {
                root.textContent = "No project found. Set `working_dir` in your .oops.yaml.";
            }
        } catch (e) {
            showError((e as Error).message);
        }
    }

    void init();
}
