import * as React from "react";
import { cn } from "@/lib/utils";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { HelpTooltip } from "@/components/ui/HelpTooltip";

interface BaseFieldProps {
  label?: string;
  required?: boolean;
  helpText?: string;
  tooltip?: string;
  error?: string;
  className?: string;
  id?: string;
}

type FieldInputProps = BaseFieldProps &
  Omit<React.InputHTMLAttributes<HTMLInputElement>, keyof BaseFieldProps> & {
    variant?: "input";
  };
type FieldSelectProps = BaseFieldProps &
  Omit<React.SelectHTMLAttributes<HTMLSelectElement>, keyof BaseFieldProps> & {
    variant: "select";
    children: React.ReactNode;
  };
type FieldTextareaProps = BaseFieldProps &
  Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, keyof BaseFieldProps> & {
    variant: "textarea";
  };

type FieldProps = FieldInputProps | FieldSelectProps | FieldTextareaProps;

function generateId(label: string) {
  return `field-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

function stripBase<T extends BaseFieldProps>(props: T): Omit<T, keyof BaseFieldProps> {
  const { label: _l, required: _r, helpText: _h, tooltip: _t, error: _e, className: _c, id: _id, ...rest } = props;
  void _l; void _r; void _h; void _t; void _e; void _c; void _id;
  return rest as Omit<T, keyof BaseFieldProps>;
}

export function Field(props: FieldProps): React.ReactElement {
  const { label, required, helpText, tooltip, error, className, id } = props;

  const autoId = React.useId();
  const fieldId = id ?? (label ? generateId(label) : `field${autoId}`);
  const variant = props.variant ?? "input";
  const describedById = error ? `${fieldId}-error` : helpText ? `${fieldId}-help` : undefined;

  const sharedProps = {
    id: fieldId,
    "aria-invalid": error ? (true as const) : undefined,
    "aria-describedby": describedById,
  };

  const rest = stripBase(props);

  let control: React.ReactNode;
  if (variant === "select") {
    control = (
      <Select {...sharedProps} {...(rest as React.SelectHTMLAttributes<HTMLSelectElement>)}>
        {(props as FieldSelectProps).children}
      </Select>
    );
  } else if (variant === "textarea") {
    control = <Textarea {...sharedProps} {...(rest as React.TextareaHTMLAttributes<HTMLTextAreaElement>)} />;
  } else {
    control = <Input {...sharedProps} {...(rest as React.InputHTMLAttributes<HTMLInputElement>)} />;
  }

  return (
    <div className={cn("space-y-0", className)}>
      {(label || tooltip) && (
        <div className="flex items-center gap-1.5 mb-1.5">
          {label && (
            <Label htmlFor={fieldId} className="mb-0">
              {label}
              {required && <span className="text-foreground ml-0.5" aria-hidden="true">*</span>}
            </Label>
          )}
          {tooltip && <HelpTooltip content={tooltip} />}
        </div>
      )}
      {control}
      {helpText && !error && (
        <p id={`${fieldId}-help`} className="text-xs text-muted-foreground mt-1">
          {helpText}
        </p>
      )}
      {error && (
        <p id={`${fieldId}-error`} className="text-xs text-foreground mt-1 font-medium">
          {error}
        </p>
      )}
    </div>
  );
}
