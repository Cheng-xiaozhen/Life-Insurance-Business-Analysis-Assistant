"use client";
import { useId, useState } from "react";
import { X } from "lucide-react";
import { Button } from "./button";
import { Input } from "./input";

export function TagInput({
  name,
  label,
  defaultValue,
}: {
  name: string;
  label: string;
  defaultValue: string[];
}) {
  const id = useId();
  const [tags, setTags] = useState(defaultValue);
  const [input, setInput] = useState("");
  function add() {
    const values = input
      .split(/[\n,，;；]+/)
      .map((value) => value.trim())
      .filter(Boolean);
    setTags((current) => [...new Set([...current, ...values])]);
    setInput("");
  }
  return (
    <div className="grid min-w-0 content-start gap-2 text-sm">
      <label
        htmlFor={id}
        className="font-medium"
      >
        {label}
      </label>
      {tags.length > 0 && (
        <ul
          aria-label={`${label}标签`}
          className="flex flex-wrap gap-2"
        >
          {tags.map((tag) => (
            <li
              key={tag}
              className="flex max-w-full items-center gap-1 rounded-md bg-teal-50 py-1 pr-1 pl-2.5 text-[#2F6868]"
            >
              <input
                type="hidden"
                name={name}
                value={tag}
              />
              <span className="min-w-0 break-all">{tag}</span>
              <button
                type="button"
                aria-label={`删除${label}：${tag}`}
                onClick={() =>
                  setTags((current) => current.filter((value) => value !== tag))
                }
                className="shrink-0 rounded p-1 hover:bg-teal-100 focus-visible:outline-2 focus-visible:outline-offset-2"
              >
                <X
                  aria-hidden="true"
                  className="size-3.5"
                />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <Input
          id={id}
          name={name}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="输入新值，按回车添加"
          aria-describedby={`${id}-hint`}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.nativeEvent.isComposing) {
              event.preventDefault();
              add();
            }
          }}
        />
        <Button
          type="button"
          variant="outline"
          disabled={!input.trim()}
          aria-label={`添加${label}`}
          onClick={add}
        >
          添加
        </Button>
      </div>
      <p
        id={`${id}-hint`}
        className="text-muted-foreground text-xs"
      >
        可用逗号分隔添加多个值，重复值自动合并。
      </p>
    </div>
  );
}
