const kindInputs = document.querySelectorAll('input[name="kind"]');
const categorySelect = document.querySelector("#category");

function updateCategories() {
  if (!categorySelect) return;

  const selectedKind = document.querySelector('input[name="kind"]:checked')?.value;
  for (const group of categorySelect.querySelectorAll("optgroup")) {
    group.hidden = (selectedKind === "income") !== (group.label === "Income");
  }

  const selectedGroup = [...categorySelect.querySelectorAll("optgroup")].find(
    (group) => !group.hidden,
  );
  if (selectedGroup && !selectedGroup.contains(categorySelect.selectedOptions[0])) {
    categorySelect.value = selectedGroup.querySelector("option").value;
  }
}

for (const input of kindInputs) {
  input.addEventListener("change", updateCategories);
}
updateCategories();
