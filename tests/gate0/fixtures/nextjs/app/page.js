import Link from "next/link";

export default function Home() {
  return (
    <main>
      <h1>Shop admin</h1>
      <Link href="/orders">Orders</Link>
    </main>
  );
}
