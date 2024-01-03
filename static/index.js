let AUTOCOMPLETE_CONTROLLER = new AbortController();

function disableEmptyInputs(form) {
  const controls = form.elements;
  for (let i = 0; i < controls.length; i++) {
    controls[i].disabled = controls[i].value === "";
  }
}

async function queryAutocomplete(input) {
  const requestResults = async (q) => {
    // Cancel existing request.
    AUTOCOMPLETE_CONTROLLER.abort();
    AUTOCOMPLETE_CONTROLLER = new AbortController();
    if (q.length <= 1) return [];

    // Run request.
    const url = `/autocomplete?` + new URLSearchParams({q});
    const options = {signal: AUTOCOMPLETE_CONTROLLER.signal};
    return await (await fetch(url, options)).json();
  };

  const replaceResults = (results) => {
    // Retrieve and clear existing suggestions.
    const list = document.querySelector("#autocompletion-list");
    list.innerHTML = "";

    // Add suggestions.
    for (const [category, term, query] of results) {
      const onClick = () => {
        // Guaranteed to be non-empty.
        input.value = query + " ";

        // Clear results and focus input.
        list.innerHTML = "";
        input.focus();
      };

      const item = document.createElement("li");
      item.innerHTML = `<b>${category}:</b> ${term}`;
      item.onclick = () => onClick();
      list.append(item);
    }
  };

  try {
    const results = await requestResults(input.value);
    replaceResults(results);
  } catch (_error) {
    // Request was overriden and aborted.
  }
}
