import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold tracking-tight">ZenFlux App</h1>
        <p className="text-muted-foreground">Start building your application here.</p>
        <Button>Click me</Button>
      </div>
    </div>
  );
}
