export default function Stub({ title, note }: { title: string; note: string }) {
  return (
    <section className="wrap stub">
      <h1>{title}</h1>
      <p className="muted">{note}</p>
    </section>
  );
}