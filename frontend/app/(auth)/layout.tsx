export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <h1 className="mb-8 text-center text-2xl font-semibold">CodeAtlas</h1>
        <div className="rounded-lg border p-6 shadow-sm">{children}</div>
      </div>
    </div>
  );
}
