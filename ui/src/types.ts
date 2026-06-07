// Types derived from the real machine payloads (presenters' to_machine()).
// The format JSON Schema (output/schema/analyze_ir_v2.json) stays the source
// of truth for descriptors; these interfaces mirror the node shapes.

export interface Metadata {
  command?: string;
  project_name?: string;
  generated_at?: string;
  git_branch?: string;
  git_commit?: string;
  tool_version?: string;
  odoo_version?: string;
  [k: string]: unknown;
}

export interface Loc {
  python: number;
  xml: number;
  javascript: number;
  docs: number;
  total?: number;
}

export interface Addon {
  technical_name: string;
  classification: string;
  version: string | null;
  submodule: string | null;
  author: string | null;
  loc: Loc | null;
  loc_pct: number;
  [k: string]: unknown;
}

export interface Stat { name: string; label?: string; value: number | string; }
export interface MetricGroup { kind?: string; label: string; values: Stat[]; }

/** `addons list` payload. */
export interface ListPayload {
  data: Addon[];
  metrics: MetricGroup[];
  warnings: string[];
  metadata: Metadata;
}

/** Anything with a discriminating metadata.command. */
export interface Payload { metadata: Metadata; [k: string]: unknown; }

// ----- DocModel types (project serve / analyze) -----

export interface RefObject {
  kind: "link" | "external";
  path?: string;
  anchor?: string;
  name?: string;
  origin?: string;
}

export interface FieldNode {
  id: string;
  name: string;
  type?: string;
  label?: string;
  label_inferred?: boolean;
  help?: string;
  required?: boolean;
  readonly?: boolean;
  store?: boolean;
  compute?: string;
  origin_status?: string;
  comodel_ref?: RefObject;
  overrides?: { origin_module?: string; origin?: string };
  [k: string]: unknown;
}

export interface MethodNode {
  id: string;
  name: string;
  is_override?: boolean;
  is_inherited?: boolean;
  section?: string;
  signature?: string;
  decorators?: string[];
  line_start?: number;
  line_end?: number;
  overrides?: { module?: string; model?: string; id?: string };
  docstring?: string;
  [k: string]: unknown;
}

export interface ModelNode {
  id: string;
  model: string;
  status?: string;
  ancestor_module?: string;
  [k: string]: unknown;
}

export interface ViewNode {
  id: string;
  xml_id?: string;
  type?: string;
  [k: string]: unknown;
}

export interface Structure {
  data?: Record<string, Record<string, number>>;
  static_by_ext?: Record<string, number>;
  controllers_py?: number;
  wizard_py?: number;
  report_py?: number;
}

export interface InventoryNode {
  classification?: string;
  version?: string;
  submodule?: string;
  branch?: string;
  loc?: Loc;
  [k: string]: unknown;
}

export interface ContributionEntry {
  module: string;
  model_node?: ModelNode;
  fields?: FieldNode[];
  methods?: MethodNode[];
  views?: ViewNode[];
}

export interface BareModelEntry {
  description?: string;
  description_inherited_from?: string;
  contributions: ContributionEntry[];
}

export interface ModuleEntry {
  module: string;
  inventory?: InventoryNode;
  manifest?: Record<string, unknown>;
  readme?: { present?: boolean; content?: string };
  depends?: string[];
  metrics?: Record<string, unknown>;
  loc?: Record<string, unknown>;
  structure?: Structure;
  not_analysed?: string[];
  models?: ModelNode[];
  fields?: FieldNode[];
  methods?: MethodNode[];
  domain_profile?: Record<string, unknown>;
  _locTotal?: number;
}

/** JSON schema shape used by descriptorTitle / descriptorKind. */
export interface Schema {
  definitions?: Record<string, {
    properties?: Record<string, { title?: string; "x-kind"?: string; [k: string]: unknown }>;
  }>;
}

/** `project serve` payload. */
export interface ServePayload {
  modules: ModuleEntry[];
  models_by_bare: Record<string, BareModelEntry>;
  schema?: Schema;
  metadata: Metadata;
  warnings?: string[];
}
