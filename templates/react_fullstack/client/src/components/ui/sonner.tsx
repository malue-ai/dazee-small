import { Toaster as Sonner } from "sonner";

import { cn } from "@/lib/utils";

type ToasterProps = React.ComponentProps<typeof Sonner>;

/**
 * Toaster 组件 - 基于 sonner 的 toast 通知组件
 * 
 * 使用方法：
 * import { toast } from "sonner"
 * toast("消息内容")
 * toast.success("成功消息")
 * toast.error("错误消息")
 */
function Toaster({ ...props }: ToasterProps) {
  return (
    <Sonner
      className={cn("toaster group")}
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-background group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg",
          description: "group-[.toast]:text-muted-foreground",
          actionButton:
            "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton:
            "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
        },
      }}
      {...props}
    />
  );
}

export { Toaster };
