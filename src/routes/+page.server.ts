import { supabase } from "$lib/supabaseClient";

export async function load() {
  const { data } = await supabase
    .from("readings")
    .select()
    .order("created_at", { ascending: false });
  return {
    readings: data ?? [],
  };
}
