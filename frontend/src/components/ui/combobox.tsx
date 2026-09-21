import * as React from "react"
import { Check, ChevronsUpDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

interface ComboboxProps {
  value: string
  onChange: (value: string) => void
  options: string[]
  placeholder?: string
  searchPlaceholder?: string
  emptyText?: string
  allowCustomInput?: boolean
  className?: string
  disabled?: boolean
}

const formatDisplay = (text: string, maxLen = 26) => {
  if (!text) return ''
  if (text.length <= maxLen) return text
  return `${text.slice(0, maxLen)}...`
}

export function Combobox({
  value,
  onChange,
  options,
  placeholder = "选择或输入模型...",
  searchPlaceholder = "🔍 搜索过滤模型...",
  emptyText = "未找到匹配模型 (可直接在上方输入)",
  allowCustomInput = true,
  className,
  disabled = false,
}: ComboboxProps) {
  const [open, setOpen] = React.useState(false)
  const [inputValue, setInputValue] = React.useState("")

  return (
    <Popover open={open} onOpenChange={setOpen} modal={true}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className={cn(
            "w-full max-w-full h-9 justify-between text-xs font-normal bg-card border-input px-3 hover:bg-card/80 min-w-0 overflow-hidden",
            !value && "text-muted-foreground",
            className
          )}
          title={value || placeholder}
        >
          <span className="truncate block min-w-0 flex-1 text-left">
            {formatDisplay(value || placeholder, 26)}
          </span>
          <ChevronsUpDown className="ml-2 h-3.5 w-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[320px] p-0 shadow-2xl border bg-popover rounded-xl overscroll-contain"
        align="start"
        onWheel={(e) => e.stopPropagation()}
      >
        <Command>
          <CommandInput
            placeholder={searchPlaceholder}
            value={inputValue}
            onValueChange={setInputValue}
          />
          <CommandList>
            <CommandEmpty className="p-3 text-center text-xs text-muted-foreground">
              <div>{emptyText}</div>
              {allowCustomInput && inputValue.trim() && (
                <Button
                  size="sm"
                  variant="secondary"
                  className="mt-2 text-xs w-full"
                  onClick={() => {
                    onChange(inputValue.trim())
                    setOpen(false)
                  }}
                >
                  使用自定义: "{inputValue.trim()}"
                </Button>
              )}
            </CommandEmpty>
            <CommandGroup>
              {options.map((option) => (
                <CommandItem
                  key={option}
                  value={option}
                  onSelect={(currentValue) => {
                    onChange(currentValue)
                    setOpen(false)
                  }}
                  className="text-xs flex items-center justify-between"
                  title={option}
                >
                  <span className="truncate block min-w-0 flex-1 text-left">
                    {formatDisplay(option, 34)}
                  </span>
                  <Check
                    className={cn(
                      "ml-2 h-3.5 w-3.5 text-primary shrink-0",
                      value === option ? "opacity-100" : "opacity-0"
                    )}
                  />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
