"use client";

import {
  Check,
  ChevronLeft,
  ClipboardPaste,
  Code2,
  FileCode,
  FileUp,
  Pencil,
  Plus,
  Repeat,
  Trash2,
} from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import {
  SCRIPT_TEMPLATES,
  type SavedScript,
  type ScriptKind,
  useScriptStore,
} from "@/lib/script-store";
import { cn } from "@/lib/utils";

const scriptKinds = [
  {
    value: "reduce" as const,
    label: "Reduce Script",
    description: "Combine model answers into one",
    Icon: Code2,
  },
  {
    value: "loop" as const,
    label: "Response Loop",
    description: "Multi-turn loop across models",
    Icon: Repeat,
  },
];

export default function ScriptsPage() {
  const scripts = useScriptStore((state) => state.scripts);
  const saveScript = useScriptStore((state) => state.saveScript);
  const removeScript = useScriptStore((state) => state.removeScript);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftKind, setDraftKind] = useState<ScriptKind>("reduce");
  const [draftName, setDraftName] = useState("");
  const [draftCode, setDraftCode] = useState(SCRIPT_TEMPLATES.reduce);
  const fileRef = useRef<HTMLInputElement>(null);
  const editing = scripts.find((script) => script.id === editingId) ?? null;
  const editorOpen = creating || editing !== null;

  function startCreate() {
    setCreating(true);
    setEditingId(null);
    setDraftKind("reduce");
    setDraftName("");
    setDraftCode(SCRIPT_TEMPLATES.reduce);
  }

  function startEdit(script: SavedScript) {
    setCreating(false);
    setEditingId(script.id);
    setDraftKind(script.kind);
    setDraftName(script.name);
    setDraftCode(script.code);
  }

  function closeEditor() {
    setCreating(false);
    setEditingId(null);
  }

  function changeKind(kind: ScriptKind) {
    const isTemplate =
      !draftCode.trim() ||
      draftCode === SCRIPT_TEMPLATES.reduce ||
      draftCode === SCRIPT_TEMPLATES.loop;
    setDraftKind(kind);
    if (isTemplate) setDraftCode(SCRIPT_TEMPLATES[kind]);
  }

  function save() {
    const defaultName = `${draftKind}-${window.crypto.randomUUID().slice(0, 6)}.py`;
    saveScript({
      id: editing?.id ?? window.crypto.randomUUID(),
      name: draftName.trim() || defaultName,
      kind: draftKind,
      code: draftCode,
      createdAt:
        editing?.createdAt ??
        new Date().toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
        }),
    });
    closeEditor();
  }

  function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setDraftName(file.name);
    const reader = new FileReader();
    reader.onload = () => setDraftCode(String(reader.result ?? ""));
    reader.readAsText(file);
    event.target.value = "";
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b px-5 py-5 sm:px-8">
        <div className="min-w-0 flex-1">
          <h1 className="text-base font-semibold">Scripts</h1>
          <p className="mt-1 text-xs text-muted-foreground">
            Python reduce scripts and response loops you can reference from any
            ensemble.
          </p>
        </div>
        {!editorOpen && (
          <Button size="sm" className="rounded-lg" onClick={startCreate}>
            <Plus className="size-3.5" />
            Add Script
          </Button>
        )}
      </header>

      {editorOpen ? (
        <main className="min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-8">
          <Button
            variant="ghost"
            size="sm"
            className="mb-6 -ml-3 text-muted-foreground"
            onClick={closeEditor}
          >
            <ChevronLeft className="size-3.5" />
            All scripts
          </Button>

          <div className="flex max-w-2xl flex-col gap-5">
            <section>
              <p className="mb-2 text-xs text-muted-foreground">Type</p>
              <RadioGroup
                value={draftKind}
                onValueChange={(value) => changeKind(value as ScriptKind)}
                aria-label="Script type"
                className="grid-cols-2 gap-3"
              >
                {scriptKinds.map(({ value, label, description, Icon }) => (
                  <label
                    key={value}
                    htmlFor={`script-kind-${value}`}
                    className={cn(
                      "flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition-colors",
                      draftKind === value
                        ? "border-primary/50 bg-primary/5"
                        : "hover:bg-muted/20",
                    )}
                  >
                    <RadioGroupItem
                      id={`script-kind-${value}`}
                      value={value}
                      className="mt-0.5"
                    />
                    <Icon className="mt-0.5 size-4 shrink-0 text-primary" />
                    <span>
                      <span className="block text-sm font-medium">{label}</span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        {description}
                      </span>
                    </span>
                  </label>
                ))}
              </RadioGroup>
            </section>

            <section>
              <label
                htmlFor="script-name"
                className="mb-2 block text-xs text-muted-foreground"
              >
                File Name
              </label>
              <div className="relative w-80">
                <FileCode className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="script-name"
                  value={draftName}
                  placeholder="my_reducer.py"
                  className="pl-9 font-mono"
                  onChange={(event) => setDraftName(event.target.value)}
                />
              </div>
            </section>

            <section>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <label htmlFor="script-code" className="text-xs text-muted-foreground">
                  Python Code
                </label>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => fileRef.current?.click()}
                  >
                    <FileUp className="size-3.5" />
                    Upload file
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setDraftCode(SCRIPT_TEMPLATES[draftKind])}
                  >
                    <ClipboardPaste className="size-3.5" />
                    Reset template
                  </Button>
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".py,text/x-python,text/plain"
                    className="hidden"
                    onChange={upload}
                  />
                </div>
              </div>
              <Textarea
                id="script-code"
                value={draftCode}
                rows={16}
                spellCheck={false}
                placeholder="# paste your Python here"
                className="resize-y rounded-xl font-mono text-sm leading-relaxed"
                onChange={(event) => setDraftCode(event.target.value)}
              />
            </section>

            <div className="flex items-center gap-2">
              <Button className="rounded-xl" onClick={save}>
                <Check className="size-4" />
                {editing ? "Save Changes" : "Save Script"}
              </Button>
              <Button variant="outline" className="rounded-xl" onClick={closeEditor}>
                Cancel
              </Button>
            </div>
          </div>
        </main>
      ) : (
        <main className="min-h-0 flex-1 overflow-y-auto px-5 py-8 sm:px-8">
          {scripts.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
              <FileCode className="size-7 text-muted-foreground/30" />
              <p className="text-sm text-muted-foreground">No scripts yet.</p>
              <Button size="sm" onClick={startCreate}>
                <Plus className="size-3.5" />
                Add Script
              </Button>
            </div>
          ) : (
            <div className="flex max-w-3xl flex-col gap-8">
              {scriptKinds.map(({ value, label, Icon }) => {
                const items = scripts.filter((script) => script.kind === value);
                if (items.length === 0) return null;
                return (
                  <section key={value}>
                    <div className="mb-3 flex items-center gap-2">
                      <Icon className="size-3.5 text-muted-foreground" />
                      <h2 className="text-xs text-muted-foreground">{label}s</h2>
                    </div>
                    <div className="flex flex-col gap-3">
                      {items.map((script) => (
                        <article
                          key={script.id}
                          className="overflow-hidden rounded-xl border bg-card"
                        >
                          <header className="flex items-center justify-between gap-3 border-b border-border/50 px-4 py-3">
                            <div className="flex min-w-0 items-center gap-2.5">
                              <FileCode className="size-3.5 shrink-0 text-primary" />
                              <span className="truncate font-mono text-sm">
                                {script.name}
                              </span>
                              <span className="shrink-0 text-xs text-muted-foreground">
                                · {script.createdAt}
                              </span>
                            </div>
                            <div className="flex items-center gap-1">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="size-8 text-muted-foreground"
                                aria-label={`Edit ${script.name}`}
                                onClick={() => startEdit(script)}
                              >
                                <Pencil className="size-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="size-8 text-muted-foreground hover:text-destructive"
                                aria-label={`Delete ${script.name}`}
                                onClick={() => removeScript(script.id)}
                              >
                                <Trash2 className="size-3.5" />
                              </Button>
                            </div>
                          </header>
                          <pre className="max-h-36 overflow-auto px-4 py-3 font-mono text-xs leading-relaxed text-muted-foreground">
                            {script.code.trim()}
                          </pre>
                        </article>
                      ))}
                    </div>
                  </section>
                );
              })}
            </div>
          )}
        </main>
      )}
    </div>
  );
}
