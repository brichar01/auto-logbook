-- Records the files a Neovim session wrote to the logbook journal when Neovim exits.
-- Set vim.g.auto_logbook_disable = true to turn it off.

local started = os.time()
local written = {}
local group = vim.api.nvim_create_augroup("auto_logbook", { clear = true })

vim.api.nvim_create_autocmd("BufWritePost", {
  group = group,
  callback = function(event)
    local name = vim.api.nvim_buf_get_name(event.buf)
    if name ~= "" and vim.bo[event.buf].buftype == "" then
      written[vim.fn.fnamemodify(name, ":p")] = true
    end
  end,
})

vim.api.nvim_create_autocmd("VimLeavePre", {
  group = group,
  callback = function()
    local files = vim.tbl_keys(written)

    if vim.g.auto_logbook_disable or #files == 0 then
      return
    end

    if vim.fn.executable("logbook") == 0 then
      return
    end

    table.sort(files)

    local command = {
      "logbook", "capture", "nvim", "--cwd", vim.fn.getcwd(), "--started", tostring(started), "--",
    }

    vim.list_extend(command, files)
    vim.fn.system(command)
  end,
})
